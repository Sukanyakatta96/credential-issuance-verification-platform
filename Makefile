PY ?= python3

.PHONY: setup data-starter data-full seed demo run test docs package

setup:
	$(PY) -m pip install -r requirements.txt
	$(PY) scripts/init_env.py

data-starter:
	$(PY) -m datagen.generate --scale starter --validate --check-reproducibility

data-full:
	$(PY) -m datagen.generate --scale full --validate --check-reproducibility

seed:
	$(PY) -m app.cli seed --data-dir $(or $(DATA),data/starter) --reset

demo:
	$(PY) -m app.cli demo-users

run:
	$(PY) -m app.cli serve

test:
	./scripts/run_tests.sh

docs:
	$(PY) scripts/generate_docs.py

package:
	./scripts/package.sh
