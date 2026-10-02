from pathlib import Path
import pytest

from symdiv.extract import extract_sites


def test_extracts_exact_denominator():
    root = Path(__file__).resolve().parents[1]
    sites = extract_sites(root / "benchmarks/pilot/sources/c07_difference_equal.c")
    assert len(sites) == 1
    assert sites[0].function == "case07"
    assert sites[0].operator == "/"
    assert sites[0].denominator == "(x - y)"



def test_portable_site_identity_and_integer_scope(tmp_path):
    source='/* 中文 */\ndouble a(double d){return 1.0/d;}\nint b(int d){int n=42;n/=d;n%=d;return n;}\n'
    first=tmp_path/'first.c'; first.write_text(source)
    second=tmp_path/'copy.c'; second.write_text(source)
    sites=extract_sites(first)
    assert [s.site_id for s in sites]==[s.site_id for s in extract_sites(second)]
    assert [s.operator for s in sites]==['/=','%=']
    assert all(s.denominator=='d' for s in sites)
    assert all(s.function=='b' and s.line==3 for s in sites)


def test_unmaterialized_preprocessing_is_rejected(tmp_path):
    import pytest
    path=tmp_path/'macro.c';path.write_text('#define D 0\nint f(void){return 42/D;}')
    with pytest.raises(ValueError,match='preprocess'): extract_sites(path)
    path.write_text('int f(void){return 42/__LINE__;}')
    with pytest.raises(ValueError,match='preprocess'): extract_sites(path)


@pytest.mark.parametrize('expression,expected_count', [
    ('x/2/0',2), ('x/2/3/0',3), ('x%2%0',2), ('x /* 注释 */ /2 /* another */ /0',2),
])
def test_nested_same_operator_sites_do_not_alias(tmp_path, expression, expected_count):
    import z3
    from symdiv.search import prepare, Search
    from symdiv.ground import build_context
    path=tmp_path/'nested.c'
    path.write_text('int f(int x){return '+expression+';}')
    prepared=prepare(path)
    sites=prepared['sites']
    assert len(sites)==expected_count
    assert len({s.site_id for s in sites})==len(sites)
    assert len([s for s in sites if s.denominator=='0'])==1
    contexts=build_context(path,sites)
    for site in sites:
        if site.denominator=='0':continue
        for reach in contexts[site.site_id].reaches:
            solver=z3.Solver();solver.add(*reach.state.constraints,reach.denominator==0)
            assert solver.check()==z3.unsat
    finding=Search(prepared).advance()['findings'][0]
    assert finding['site']['denominator']=='0'
    last_operator=path.read_text().encode().rfind(b'/' if '/' in expression else b'%')
    assert finding['site']['column']==last_operator+1
