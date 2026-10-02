from symdiv.evaluate import metrics


def test_metrics():
    rows = [
        {"expected": True, "predicted": True},
        {"expected": True, "predicted": False},
        {"expected": False, "predicted": True},
        {"expected": False, "predicted": False},
    ]
    result = metrics(rows)
    assert result["tp"] == 1
    assert result["fp"] == 1
    assert result["tn"] == 1
    assert result["fn"] == 1
    assert result["f1"] == 0.5



import pytest
from symdiv.evaluate import evaluate


@pytest.mark.parametrize('cases', [
    [],
    [{'id':'a','prediction':False,'completed':False}],
    [{'id':'a','prediction':False}],
    [{'id':'a','prediction':False,'completed':True}]*2,
    [{'id':'unexpected','prediction':False,'completed':True}],
    [{'id':'a','prediction':None,'completed':True}],
])
def test_incomplete_or_malformed_run_cannot_be_scored(cases):
    with pytest.raises(ValueError):
        evaluate({'cases':[{'id':'a','expected_bug':False}]},{'test':{'cases':cases}})
