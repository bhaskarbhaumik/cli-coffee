# ══════════════════════════════════════════════════════════════════════════════
#  coffee — build, deploy and repository management
#
#  Written for GNU Make 3.81 (the version Apple ships as /usr/bin/make), so it
#  avoids .ONESHELL, $(file ...) and other 3.82+ features.
#
#  Quick start:
#      make help              list every target
#      make install           deploy `coffee` into ~/.local/bin
#      make repo push         create the private GitHub repo and push
# ══════════════════════════════════════════════════════════════════════════════

SHELL          := /bin/bash
.SHELLFLAGS    := -eu -o pipefail -c
.DEFAULT_GOAL  := help
.SUFFIXES:

# ── Identity ──────────────────────────────────────────────────────────────────
NAME           := coffee
PKG            := coffee
DIST_NAME      := cli_coffee
TOOL_NAME      := cli-coffee
SRC_DIR        := src/$(PKG)
TEST_DIR       := tests
VERSION        := $(shell sed -n 's/^version *= *"\(.*\)"/\1/p' pyproject.toml | head -1)
DESCRIPTION    := Keep an Apple Silicon Mac awake, with style

# ── Deployment ────────────────────────────────────────────────────────────────
#  Override any of these:  make install DESTDIR=/usr/local/bin
DESTDIR        ?= $(HOME)/.local/bin
UV             ?= uv
PYTHON_VERSION ?= 3.14
TOOL_BIN       := $(HOME)/.local/share/uv/tools/$(TOOL_NAME)/bin/$(NAME)
INSTALLED      := $(DESTDIR)/$(NAME)

# ── GitHub ────────────────────────────────────────────────────────────────────
GH             ?= gh
GIT            ?= git
GH_OWNER       ?= $(shell $(GH) api user -q .login 2>/dev/null)
REPO           ?= cli-coffee
REPO_SLUG      := $(GH_OWNER)/$(REPO)
VISIBILITY     ?= private
BRANCH         ?= main
REMOTE         ?= origin
MSG            ?= chore: update

# ── Build artefacts ───────────────────────────────────────────────────────────
DIST           := dist
WHEEL           = $(shell ls -t $(DIST)/$(DIST_NAME)-*.whl 2>/dev/null | head -1)
SOURCES        := $(shell find $(SRC_DIR) -name '*.py' 2>/dev/null) pyproject.toml README.md

# ── Cosmetics ─────────────────────────────────────────────────────────────────
C_RST := \033[0m
C_HDR := \033[1;36m
C_TGT := \033[1;33m
C_DIM := \033[2;37m
C_OK  := \033[1;32m
C_ERR := \033[1;31m
TICK  := $(shell printf '\342\234\224')
CROSS := $(shell printf '\342\234\230')
ARROW := $(shell printf '\342\236\234')

define say
	@printf "$(C_HDR)$(ARROW)$(C_RST) %s\n" $(1)
endef

define ok
	@printf "$(C_OK)$(TICK)$(C_RST) %s\n" $(1)
endef

.PHONY: help version info \
        venv sync build clean distclean \
        install install-symlink uninstall reinstall verify \
        lint fmt check smoke parity pytest test demo \
        repo remote commit push pull status tag release ci

# ══════════════════════════════════════════════════════════════════════════════
#  Help
# ══════════════════════════════════════════════════════════════════════════════

help: ## Show this help
	@printf "\n$(C_HDR)$(NAME)$(C_RST) $(C_DIM)v$(VERSION)$(C_RST) — $(DESCRIPTION)\n\n"
	@printf "$(C_HDR)Usage:$(C_RST) make $(C_TGT)<target>$(C_RST) [VAR=value ...]\n\n"
	@printf "$(C_HDR)Targets:$(C_RST)\n"
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | sort \
	  | awk 'BEGIN {FS = ":.*?## "} {printf "  $(C_TGT)%-16s$(C_RST) %s\n", $$1, $$2}'
	@printf "\n$(C_HDR)Variables:$(C_RST)\n"
	@printf "  $(C_TGT)%-16s$(C_RST) %s\n" "DESTDIR"    "$(DESTDIR)"
	@printf "  $(C_TGT)%-16s$(C_RST) %s\n" "REPO"       "$(REPO_SLUG) ($(VISIBILITY))"
	@printf "  $(C_TGT)%-16s$(C_RST) %s\n" "BRANCH"     "$(BRANCH)"
	@printf "  $(C_TGT)%-16s$(C_RST) %s\n" "PYTHON_VER" "$(PYTHON_VERSION)"
	@printf "\n"

version: ## Print the project version
	@echo "$(VERSION)"

info: ## Show resolved configuration
	@printf "name           %s\n" "$(NAME)"
	@printf "version        %s\n" "$(VERSION)"
	@printf "source         %s\n" "$(SRC_DIR)"
	@printf "destdir        %s\n" "$(DESTDIR)"
	@printf "installed at   %s\n" "$(INSTALLED)"
	@printf "uv tool bin    %s\n" "$(TOOL_BIN)"
	@printf "github repo    %s (%s)\n" "$(REPO_SLUG)" "$(VISIBILITY)"
	@printf "branch/remote  %s / %s\n" "$(BRANCH)" "$(REMOTE)"
	@printf "wheel          %s\n" "$(if $(WHEEL),$(WHEEL),<none — run make build>)"

# ══════════════════════════════════════════════════════════════════════════════
#  Build
# ══════════════════════════════════════════════════════════════════════════════

venv: ## Create the development virtualenv
	$(call say,"creating .venv with Python $(PYTHON_VERSION)")
	@$(UV) venv --python $(PYTHON_VERSION)
	$(call ok,".venv ready")

sync: ## Install dependencies into the development virtualenv
	$(call say,"syncing dependencies")
	@$(UV) pip install -e .
	$(call ok,"dependencies synced")

build: $(DIST)/.stamp ## Build the wheel and sdist

$(DIST)/.stamp: $(SOURCES)
	$(call say,"building $(NAME) $(VERSION)")
	@rm -rf $(DIST)
	@$(UV) build --out-dir $(DIST)
	@touch $@
	@ls -1 $(DIST)/*.whl $(DIST)/*.tar.gz
	$(call ok,"build complete")

clean: ## Remove build artefacts and caches
	$(call say,"cleaning")
	@rm -rf $(DIST) build *.egg-info .ruff_cache .pytest_cache
	@find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	$(call ok,"cleaned")

distclean: clean ## Also remove the virtualenv
	@rm -rf .venv
	$(call ok,"removed .venv")

# ══════════════════════════════════════════════════════════════════════════════
#  Install / uninstall
# ══════════════════════════════════════════════════════════════════════════════

install: build ## Install coffee into DESTDIR (default ~/.local/bin)
	$(call say,"installing $(NAME) $(VERSION) via uv tool")
	@$(UV) tool install --force --python $(PYTHON_VERSION) "$(WHEEL)"
	@mkdir -p "$(DESTDIR)"
	@if [ ! -e "$(TOOL_BIN)" ]; then \
	    printf "$(C_ERR)$(CROSS)$(C_RST) uv did not produce %s\n" "$(TOOL_BIN)"; \
	    exit 1; \
	fi
	@if [ "$(DESTDIR)" != "$(HOME)/.local/bin" ] || [ ! -e "$(INSTALLED)" ]; then \
	    ln -sfn "$(TOOL_BIN)" "$(INSTALLED)"; \
	fi
	@$(MAKE) --no-print-directory verify

install-symlink: ## Install a dev launcher that runs straight from this checkout
	$(call say,"installing editable launcher into $(DESTDIR)")
	@mkdir -p "$(DESTDIR)"
	@printf '#!/bin/sh\n# generated by `make install-symlink` — runs %s from source\nexec "%s" run --project "%s" --python %s %s "$$@"\n' \
	    "$(NAME)" "$$(command -v $(UV))" "$(CURDIR)" "$(PYTHON_VERSION)" "$(NAME)" > "$(INSTALLED)"
	@chmod 755 "$(INSTALLED)"
	@$(MAKE) --no-print-directory verify

uninstall: ## Remove coffee from DESTDIR and from uv's tool store
	$(call say,"uninstalling $(NAME)")
	@rm -f "$(INSTALLED)"
	@$(UV) tool uninstall $(TOOL_NAME) 2>/dev/null || true
	$(call ok,"$(NAME) removed")

reinstall: uninstall install ## Uninstall then install

verify: ## Check that the installed coffee works and is on PATH
	@if [ ! -x "$(INSTALLED)" ] && [ ! -L "$(INSTALLED)" ]; then \
	    printf "$(C_ERR)$(CROSS)$(C_RST) not installed at %s\n" "$(INSTALLED)"; exit 1; \
	fi
	@printf "$(C_OK)$(TICK)$(C_RST) %s -> %s\n" "$(INSTALLED)" "$$("$(INSTALLED)" --version)"
	@case ":$$PATH:" in \
	  *":$(DESTDIR):"*) printf "$(C_OK)$(TICK)$(C_RST) %s is on PATH\n" "$(DESTDIR)" ;; \
	  *) printf "$(C_ERR)$(CROSS)$(C_RST) %s is NOT on PATH — add it to your shell rc\n" "$(DESTDIR)" ;; \
	esac

# ══════════════════════════════════════════════════════════════════════════════
#  Quality
# ══════════════════════════════════════════════════════════════════════════════

lint: ## Lint with ruff
	@$(UV) run --with ruff ruff check $(SRC_DIR) $(TEST_DIR)

fmt: ## Format with ruff
	@$(UV) run --with ruff ruff format $(SRC_DIR) $(TEST_DIR)
	@$(UV) run --with ruff ruff check --fix $(SRC_DIR) $(TEST_DIR)

check: ## Byte-compile every module (catches syntax errors fast)
	@$(UV) run --python $(PYTHON_VERSION) --no-project python -m compileall -q $(SRC_DIR)
	$(call ok,"all modules compile")

smoke: ## Exercise the read-only sub-commands from source
	$(call say,"smoke testing from source")
	@$(UV) run --project . --python $(PYTHON_VERSION) $(NAME) --version
	@$(UV) run --project . --python $(PYTHON_VERSION) $(NAME) doctor >/dev/null
	@$(UV) run --project . --python $(PYTHON_VERSION) $(NAME) show >/dev/null
	@$(UV) run --project . --python $(PYTHON_VERSION) $(NAME) power status >/dev/null
	@$(UV) run --project . --python $(PYTHON_VERSION) $(NAME) --dry-run power on >/dev/null
	$(call ok,"smoke tests passed")

pytest: ## Run the unit tests
	@$(UV) run --project . --python $(PYTHON_VERSION) --with pytest pytest -q $(TEST_DIR)

parity: ## Diff every panel against the reference implementation, if it is present
	@$(UV) run --project . --python $(PYTHON_VERSION) --with pytest \
	    pytest -q $(TEST_DIR)/test_parity.py -rs

test: check pytest smoke ## Run every check

ci: lint test ## Lint and test, the way CI would

demo: ## Render every panel once, as the installed coffee sees it
	@"$(INSTALLED)" show --rows

# ══════════════════════════════════════════════════════════════════════════════
#  Git / GitHub
# ══════════════════════════════════════════════════════════════════════════════

.git:
	$(call say,"initialising a git repository on $(BRANCH)")
	@$(GIT) init -b $(BRANCH)

repo: .git ## Create the private GitHub repo and wire up the remote
	@if [ -z "$(GH_OWNER)" ]; then \
	    printf "$(C_ERR)$(CROSS)$(C_RST) not logged in — run: gh auth login\n"; exit 1; \
	fi
	@if $(GH) repo view "$(REPO_SLUG)" >/dev/null 2>&1; then \
	    printf "$(C_OK)$(TICK)$(C_RST) %s already exists\n" "$(REPO_SLUG)"; \
	else \
	    printf "$(C_HDR)$(ARROW)$(C_RST) creating %s (%s)\n" "$(REPO_SLUG)" "$(VISIBILITY)"; \
	    $(GH) repo create "$(REPO_SLUG)" --$(VISIBILITY) --description "$(DESCRIPTION)" \
	        --disable-wiki; \
	fi
	@$(MAKE) --no-print-directory remote

remote: ## Point the git remote at the GitHub repo
	@url=$$($(GH) repo view "$(REPO_SLUG)" --json url -q .url 2>/dev/null); \
	if [ -z "$$url" ]; then printf "$(C_ERR)$(CROSS)$(C_RST) no such repo: %s\n" "$(REPO_SLUG)"; exit 1; fi; \
	if $(GIT) remote get-url $(REMOTE) >/dev/null 2>&1; then \
	    $(GIT) remote set-url $(REMOTE) "$$url.git"; \
	else \
	    $(GIT) remote add $(REMOTE) "$$url.git"; \
	fi; \
	printf "$(C_OK)$(TICK)$(C_RST) %s -> %s\n" "$(REMOTE)" "$$url"

status: ## Show git status and the current remote
	@$(GIT) status --short --branch
	@$(GIT) remote -v

commit: ## Stage everything and commit (MSG="...")
	@if $(GIT) diff --quiet && $(GIT) diff --cached --quiet && [ -z "$$($(GIT) ls-files --others --exclude-standard)" ]; then \
	    printf "$(C_OK)$(TICK)$(C_RST) nothing to commit\n"; \
	else \
	    $(GIT) add -A && $(GIT) commit -m "$(MSG)" && \
	    printf "$(C_OK)$(TICK)$(C_RST) committed: %s\n" "$(MSG)"; \
	fi

push: ## Push the branch, setting upstream on first push
	@if $(GIT) rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then \
	    $(GIT) push $(REMOTE) $(BRANCH); \
	else \
	    $(GIT) push -u $(REMOTE) $(BRANCH); \
	fi
	$(call ok,"pushed $(BRANCH) to $(REMOTE)")

pull: ## Fast-forward the branch from the remote
	@$(GIT) pull --ff-only $(REMOTE) $(BRANCH)

tag: ## Tag the current commit with the project version
	@$(GIT) tag -a "v$(VERSION)" -m "$(NAME) v$(VERSION)" 2>/dev/null \
	    || printf "$(C_DIM)tag v%s already exists$(C_RST)\n" "$(VERSION)"
	@$(GIT) push $(REMOTE) "v$(VERSION)"

release: test build tag ## Test, build, tag and publish a GitHub release
	@$(GH) release create "v$(VERSION)" $(DIST)/* \
	    --repo "$(REPO_SLUG)" \
	    --title "$(NAME) v$(VERSION)" \
	    --generate-notes \
	  || printf "$(C_DIM)release v%s already exists$(C_RST)\n" "$(VERSION)"
	$(call ok,"released v$(VERSION)")
