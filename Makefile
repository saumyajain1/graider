RUFF ?= .venv/bin/ruff
SHELLCHECK ?= .venv/bin/shellcheck
HADOLINT_IMAGE := hadolint/hadolint:v2.15.1@sha256:32dac94127fd60b7b7e3fbfc65e1383b9b5e25c9bfd7b8536de7a539fe68a12d
ACTIONLINT_IMAGE := rhysd/actionlint:1.7.12@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667

.PHONY: lint format format-check check

lint:
	$(RUFF) check .
	npm run lint --prefix frontend -- --max-warnings 0
	$(SHELLCHECK) backend/start.sh
	docker run --rm --interactive $(HADOLINT_IMAGE) < Dockerfile
	docker run --rm --volume "$(CURDIR):/repo:ro" --workdir /repo $(ACTIONLINT_IMAGE)

format:
	$(RUFF) format .
	npm exec -- prettier --write .

format-check:
	$(RUFF) format --check .
	npm exec -- prettier --check .

check: lint format-check
