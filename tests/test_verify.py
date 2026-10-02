from pathlib import Path
import pytest
import z3
from symdiv.extract import extract_sites
from symdiv.ground import build_context
from symdiv.expressions import ExpressionTranslator, UnsupportedExpression
from symdiv.model import Hypothesis, DivisionSite
from symdiv.verify import verify_hypothesis


def check(tmp_path, source, conditions=(), loop_bound=8, site_index=-1):
    path = tmp_path / 'subject.c'
    path.write_text(source)
    sites = extract_sites(path)
    context = build_context(path, sites, loop_bound=loop_bound)
    s = sites[site_index]
    return verify_hypothesis(s, Hypothesis(s.site_id, 'bug', list(conditions), s.denominator, 'test', 1),
                             context=context[s.site_id])


@pytest.mark.parametrize('source,accepted', [
    ('int f(int x) { return 42 / x; }', True),
    ('int f(int x) { if(x==0) return 0; return 42/x; }', False),
    ('int f(void) { int d=7; return 42/d; }', False),
    ('int f(int x) { int d=x-x; return 42/d; }', True),
    ('int f(int x) { if(x>0 && x<0) return 42/x; return 0; }', False),
    ('int f(int x) { if(x==0) return 42/x; return 0; }', True),
    ('int f(void) { int d=0; {int d=7; d++;} return 42/d; }', True),
    ('int f(void) { int d=7; {int d=0; d++;} return 42/d; }', False),
    ('int f(void) { int d=-3/2+1; return 42/d; }', True),
    ('int f(void) { int d=-3%2+1; return 42/d; }', True),
    ('int f(int x) { if(x==2147483647) {int d=x+1; return 42/(d+2147483647+1);} return 0; }', False),
    ('int f(void) { unsigned int d=4294967295u; d++; return 42/d; }', True),
    ('int f(int x) { int n=42; if(!x) n/=x; return n; }', True),
    ('int f(int x) { int n=42; if(x) n%=x; return n; }', False),
    ('int f(void) {int d=0; while(1){d=7; break;} return 42/d;}', False),
    ('int f(void) {int d=7; for(int i=0;i<1;i++){d=0;} return 42/d;}', True),
    ('int f(void) {int d=7; do {d=0;} while(0); return 42/d;}', True),
    ('int f(int x) {return x != 0 && 42/x;}', False),
    ('int f(int x) {return x == 0 || 42/x;}', False),
    ('int f(int x) {return x ? 42/x : 0;}', False),
])
def test_source_grounding(tmp_path, source, accepted):
    result=check(tmp_path, source)
    assert result.accepted is accepted, result
    assert result.status in ('verified_sat','refuted_unsat')


def test_hypothesis_is_additional_constraint(tmp_path):
    assert check(tmp_path, 'int f(int x){return 42/x;}', ['x > 0']).status == 'refuted_unsat'
    assert check(tmp_path, 'int f(int x){return 42/x;}', ['invented == 0']).status == 'inconclusive'


def test_previous_undefined_division_blocks_later_site(tmp_path):
    result = check(tmp_path, 'int f(int x){int y=1/x; return 42/x;}', site_index=1)
    assert result.status == 'refuted_unsat'


def test_loop_limit_is_not_safety(tmp_path):
    result = check(tmp_path, 'int f(int x){while(x>0)x--; return 42/(x-9);}', loop_bound=2)
    assert result.status == 'inconclusive'
    assert 'loop bound' in result.reason


@pytest.mark.parametrize('source', [
    'int f(int x){int *p=&x; return 42/(*p);}',
    'int f(int x){return 42/(x++);}',
    'int g; int f(void){g=0;return 42/g;}',
    'int f(void){static int d=7; d--;return 42/d;}',
    'int rand(void){return 7;} int f(void){int d=rand();return 42/d;}',
])
def test_unsupported_semantics_abstain(tmp_path, source):
    assert check(tmp_path, source).status == 'inconclusive'


@pytest.mark.parametrize('expression,expected', [
    ('-3 / 2',-1),('-3 % 2',-1),('3 / -2',-1),('3 % -2',1),
    ('-3 / -2',1),('-3 % -2',-1),('!0 == 2',False),('!0 == 1',True),
    ('2 < 1 < 1',True),('1 || 0 && 0',True),
])
def test_c_expression_semantics(expression,expected):
    assert str(z3.simplify(ExpressionTranslator().parse(expression))) == str(expected)


def test_source_is_mandatory():
    s=DivisionSite('s','nonexistent.c','f',1,1,'/','x','')
    assert verify_hypothesis(s,Hypothesis('s','bug',[],'x','',1)).status=='unsupported'


def test_bad_constraint_syntax():
    with pytest.raises(UnsupportedExpression): ExpressionTranslator().parse('__import__("os")')


@pytest.mark.parametrize('source', [
    'int f(void){int x=-1;x/=2u;return 42/x;}',
    'void printLine(const char *s); int f(void){int x=0;printLine(x++?"a":"b");return 42/x;}',
    'int printIntLine(int x); int f(void){int d=printIntLine(7);return 42/d;}',
    'int f(volatile int x){return 42/x;}',
])
def test_out_of_contract_conversions_and_summaries_abstain(tmp_path, source):
    assert check(tmp_path,source).status == 'inconclusive'
