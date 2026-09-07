# power-content-check
#
# `make verify` is the gate. It must exit 0 before anything is pushed.

UV ?= uv
AUDIT_REQUIREMENTS ?= .audit-requirements.txt

.PHONY: help sync fmt lint typecheck test security verify clean catalog schemas

help:
	@echo "sync       install the locked dependency set"
	@echo "fmt        format the tree"
	@echo "lint       ruff check and format check"
	@echo "typecheck  mypy in strict mode"
	@echo "test       pytest with the coverage floor"
	@echo "security   bandit and pip-audit"
	@echo "verify     everything above, in order; the gate"
	@echo "catalog    print every registered check and the requirement it cites"
	@echo "schemas    rewrite schemas/ from the model (the gate is a test, not this)"

sync:
	$(UV) sync --locked

fmt: sync
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

lint: sync
	$(UV) run ruff check .
	$(UV) run ruff format --check .

typecheck: sync
	$(UV) run mypy

test: sync
	$(UV) run pytest

# pip-audit runs against the exported lockfile rather than the installed
# environment, so that the editable install of this project itself does not
# have to be waved through with a flag that would also wave through a real
# dependency the auditor could not resolve.
security: sync
	$(UV) run bandit -q -c pyproject.toml -r src
	NO_COLOR=1 $(UV) export --locked --all-groups --no-emit-project \
		--format requirements-txt -o $(AUDIT_REQUIREMENTS)
	$(UV) run pip-audit --strict --disable-pip -r $(AUDIT_REQUIREMENTS)
	rm -f $(AUDIT_REQUIREMENTS)

verify: lint typecheck test security
	@echo "verify: OK"

catalog: sync
	$(UV) run power-content-check catalog

# Regenerating is a convenience. The gate is tests/test_schemas.py, which fails
# when the committed files and the builders disagree, so a stale schema is a red
# test rather than something `make verify` quietly rewrites underneath you.
schemas: sync
	$(UV) run python scripts/gen_schemas.py

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov dist build
	rm -f $(AUDIT_REQUIREMENTS)
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
