PYTHON := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: setup test baseline neuro neuro-smoke evaluate results report reproduce juliet-offline clean reproduce-v3 results-v3 report-v3 reproduce-v4 results-v4 report-v4 report-figures-v4

setup:
	python3 -m venv .venv
	$(PYTHON) -m pip install --upgrade 'pip>=24' 'setuptools>=68'
	$(PIP) install -e '.[dev]'

test:
	$(PYTHON) -m pytest

baseline:
	$(PYTHON) -m symdiv baseline --manifest benchmarks/juliet/manifest.json --out results/local/juliet-baseline.json

neuro:
	$(PYTHON) -m symdiv neuro --manifest benchmarks/juliet/manifest.json --config configs/v2-juliet.json --out results/local/juliet-live.json

neuro-smoke:
	$(PYTHON) -m symdiv neuro --manifest benchmarks/juliet/smoke-manifest.json --config configs/v2-juliet-smoke.json --out results/local/juliet-smoke.json

evaluate:
	$(PYTHON) -m symdiv evaluate --manifest benchmarks/pilot/manifest.json --baseline results/v2/pilot/baseline.json --neuro results/v2/pilot/neuro.json --out-dir results/v2/pilot
	$(PYTHON) -m symdiv evaluate --manifest benchmarks/juliet/manifest.json --baseline results/v2/juliet/baseline.json --neuro results/v2/juliet/neuro.json --out-dir results/v2/juliet

results:
	$(PYTHON) scripts/render_v2_results.py

report: results
	mkdir -p output/pdf
	cd report && tectonic --keep-logs --outdir ../output/pdf main.tex
	mv output/pdf/main.pdf output/pdf/symdiv-report-final.pdf

reproduce:
	$(PYTHON) scripts/reproduce.py

reproduce-v3:
	$(PYTHON) scripts/reproduce_v3.py

results-v3:
	$(PYTHON) scripts/render_v3_results.py

report-v3: results-v3
	mkdir -p output/pdf
	cd report && tectonic --keep-logs --outdir ../output/pdf v3.tex
	mv output/pdf/v3.pdf output/pdf/symdiv-report-v3.pdf

reproduce-v4:
	$(PYTHON) scripts/reproduce_v4.py

results-v4:
	$(PYTHON) scripts/summarize_v4.py
	$(PYTHON) scripts/render_v4_report.py

report-v4: results-v4
	$(PYTHON) scripts/plot_v4_report.py --check
	$(PYTHON) scripts/check_v4_report.py
	mkdir -p output/pdf
	cd report && tectonic --keep-logs --outdir ../output/pdf v4.tex
	mv output/pdf/v4.pdf output/pdf/symdiv-report-v4.pdf

# Optional regeneration: first install requirements-report.txt.
# The normal report build verifies and uses committed figure PDFs.
report-figures-v4: results-v4
	$(PYTHON) scripts/plot_v4_report.py

juliet-offline:
	$(PYTHON) scripts/import_juliet_cwe369.py --offline

clean:
	rm -rf build dist .pytest_cache src/*.egg-info
