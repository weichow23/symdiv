"""Cheap bounded if-conversion supplies *advice*, never accepted findings.

Branch assignments merge using ITE terms; bounded loops are unrolled. Generated
choices must pass the unchanged path interpreter. Unsupported summaries, UNSAT
or timeouts never prune the real frontier or establish safety. All summary node
visits and solver calls are charged before verification continues.
"""
import time
from collections import Counter

import z3
from .ground import Executor, State, type_name
from .extract import _children
from .expressions import truth, UnsupportedExpression


class SummaryLimit(Exception):
    pass


class Advice(Executor):
    def __init__(self, prepared, max_steps, max_queries, deadline, loop_bound=8):
        super().__init__(prepared["path"],prepared["sites"],prepared["root"],loop_bound)
        self.prepared=prepared
        self.max_steps=max_steps;self.max_queries=max_queries;self.deadline=deadline
        self.summary_steps=0;self.queries=0;self.decisions=[];self.goals=[]

    def record(self,node,state,denominator,active):
        self.goals.append((list(state.constraints)+[truth(active),denominator==0],list(self.decisions)))

    def tick(self):
        if self.summary_steps>=self.max_steps or time.monotonic()>=self.deadline:raise SummaryLimit()
        self.summary_steps+=1

    def choice(self,node,condition,active):
        self.decisions.append((self.prepared["node_ids"][node["id"]],condition,active))

    def walk(self,node,state,active):
        self.tick()
        children=list(_children(node));kind=node.get("kind")
        if kind=="CompoundStmt":
            names=dict(state.names)
            for child in children:active=self.walk(child,state,active)
            state.names=names
        elif kind=="DeclStmt":
            for child in children:
                before=len(state.constraints)
                self.declare(child,state)
                state.constraints[before:]=[z3.Implies(active,c) for c in state.constraints[before:]]
        elif kind=="IfStmt":
            if node.get("hasInit") or node.get("hasVar"):raise UnsupportedExpression("condition declaration")
            condition=truth(self.eval(children[0],state,active))
            self.choice(node,condition,active)
            yes,no=state.copy(),state.copy();length=len(state.constraints)
            yes_active=self.walk(children[1],yes,z3.And(active,condition))
            no_active=(self.walk(children[2],no,z3.And(active,z3.Not(condition))) if len(children)>2
                       else z3.And(active,z3.Not(condition)))
            for identity in list(state.env):
                a,b=yes.env[identity],no.env[identity]
                if a is None or b is None:
                    if a is not None or b is not None:raise UnsupportedExpression("partial initialization in summary")
                else:state.env[identity]=z3.simplify(z3.If(condition,a,b))
            state.inputs.update(yes.inputs);state.inputs.update(no.inputs)
            state.constraints += [z3.Implies(condition,z3.And(*yes.constraints[length:])),
                                  z3.Implies(z3.Not(condition),z3.And(*no.constraints[length:]))]
            active=z3.Or(yes_active,no_active)
        elif kind in ("ForStmt","WhileStmt","DoStmt"):
            names=dict(state.names)
            if kind=="ForStmt":
                raw=node.get("inner",[])
                if len(raw)!=5 or raw[1]:raise UnsupportedExpression("for summary shape")
                initial,_,condition,increment,body=raw
                if initial:active=self.walk(initial,state,active)
            elif kind=="WhileStmt":condition,body=children;increment=None
            else:body,condition=children;increment=None
            exits=[]
            for index in range(self.loop_bound+1):
                cond=z3.BoolVal(True) if not condition or (kind=="DoStmt" and index==0) else truth(self.eval(condition,state,active))
                self.choice(node,cond,active)
                exits.append(z3.And(active,z3.Not(cond)))
                active=z3.simplify(z3.And(active,cond))
                if z3.is_false(active):break
                if index==self.loop_bound:break
                active=self.walk(body,state,active)
                if increment:active=self.walk(increment,state,active)
            # General symbolic early loop exits would require merging exit
            # environments. Decline that summary rather than inventing a value.
            if sum(not z3.is_false(z3.simplify(x)) for x in exits)>1:
                raise UnsupportedExpression("symbolic loop exit summary")
            active=z3.Or(*exits);state.names=names
        elif kind=="ReturnStmt":
            if children:self.eval(children[0],state,active)
            active=z3.BoolVal(False)
        elif kind in ("BreakStmt","ContinueStmt"):
            raise UnsupportedExpression("loop control summary")
        elif kind!="NullStmt":
            self.eval(node,state,active,allow_mutation=True)
        return z3.simplify(active)

    def propose(self):
        for function in sorted({s.function for s in self.sites}):
            self.function=function;state=State();self.decisions=[]
            for param in _children(self.functions[function]):
                if param.get("kind")=="ParmVarDecl":
                    if type_name(param) not in ("int","unsigned int"):raise UnsupportedExpression("parameter type")
                    state.env[param["id"]]=self.fresh(param["name"],state,type_name(param)=="unsigned int")
                    state.names[param["name"]]=param["id"]
            body=next(c for c in _children(self.functions[function]) if c.get("kind")=="CompoundStmt")
            self.walk(body,state,z3.BoolVal(True))
        for constraints,decisions in self.goals:
            if self.queries>=self.max_queries or time.monotonic()>=self.deadline:raise SummaryLimit()
            solver=z3.Solver();solver.add(*constraints)
            solver.set(timeout=max(1,min(1000,int((self.deadline-time.monotonic())*1000))))
            self.queries+=1
            answer=solver.check()
            if answer==z3.sat:
                model=solver.model();visits=Counter();preferences={}
                for bid,condition,active in decisions:
                    if z3.is_true(model.evaluate(active,model_completion=True)):
                        visits[bid]+=1
                        preferences[(bid,visits[bid])]=z3.is_true(model.evaluate(condition,model_completion=True))
                return preferences,"sat_advice"
        return {},"no_sat_advice"


def apply_lookahead(search,prepared,config):
    start=time.monotonic()
    remaining=max(0,search.state_budget-search.visited)
    limit=min(config["lookahead_states"],remaining//2)
    summary=Advice(prepared,limit,max(0,min(config["lookahead_queries"],search.query_budget-search.queries)),
                   min(search.deadline,start+config["lookahead_seconds"]),config["loop_bound"])
    try:preferences,status=summary.propose()
    except (UnsupportedExpression,SummaryLimit) as error:
        preferences={};status=type(error).__name__+": "+str(error)
    search.visited+=summary.summary_steps
    search.queries+=summary.queries
    search.set_policy("guided" if preferences else "dfs",preferences)
    return {"status":status,"summary_states":summary.summary_steps,"summary_queries":summary.queries,
            "seconds":time.monotonic()-start,"choices":len(preferences)}
