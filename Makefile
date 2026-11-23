.PHONY: install test smoke v1 v2 compare

install:
	pip install -r requirements.txt

test:
	python -m pytest -q

smoke:
	python -m evals.run --prompt prompts/v2_improved.txt --mock --name smoke

v1:
	python -m evals.run --prompt prompts/v1_baseline.txt --name v1 --trials 3

v2:
	python -m evals.run --prompt prompts/v2_improved.txt --name v2 --trials 3

compare:
	python -m evals.compare results/v1 results/v2
