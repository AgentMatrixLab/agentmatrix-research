PYTHON ?= python
VALIDATION_CONFIG ?= configs/validation_gates.yaml

.PHONY: validate
validate:
	$(if $(FACTOR),,$(error FACTOR is required: make validate FACTOR=turnover_20d))
	$(PYTHON) -m research_core.factor_lab.cli validate --factor "$(FACTOR)" --config "$(VALIDATION_CONFIG)"
