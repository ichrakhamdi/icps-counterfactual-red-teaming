PYTHON ?= python3
PYCACHE := /tmp/isie2027_counterfactual_xai_pycache
TEXMFVAR := /tmp/isie2027_counterfactual_xai_texmf

.PHONY: demo study smoke local-gate test paper clean

demo:
	PYTHONPYCACHEPREFIX=$(PYCACHE) $(PYTHON) scripts/run_demo.py

study:
	PYTHONPYCACHEPREFIX=$(PYCACHE) $(PYTHON) scripts/run_study.py

test:
	PYTHONPYCACHEPREFIX=$(PYCACHE) $(PYTHON) -m unittest discover -s tests -v

paper:
	cd paper && TEXMFVAR=$(TEXMFVAR) pdflatex -interaction=nonstopmode -halt-on-error main.tex
	cd paper && TEXMFVAR=$(TEXMFVAR) bibtex main
	cd paper && TEXMFVAR=$(TEXMFVAR) pdflatex -interaction=nonstopmode -halt-on-error main.tex
	cd paper && TEXMFVAR=$(TEXMFVAR) pdflatex -interaction=nonstopmode -halt-on-error main.tex

clean:
	cd paper && rm -f main.aux main.bbl main.blg main.log main.out

smoke:
	PYTHONPYCACHEPREFIX=$(PYCACHE) $(PYTHON) scripts/run_local_protocol.py --config configs/smoke.json --output-dir results/smoke_jobs

local-gate:
	PYTHONPYCACHEPREFIX=$(PYCACHE) $(PYTHON) scripts/check_local.py
