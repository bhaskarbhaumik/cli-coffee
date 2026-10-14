# Version

**Current version: `0.2.0`**

## Where the version lives

`pyproject.toml` is the single source of truth:

```toml
[project]
version = "0.2.0"
```

Everything else reads from it:

| consumer                | how it gets the version                                |
| ----------------------- | ------------------------------------------------------ |
| `coffee --version`      | `importlib.metadata.version("cli-coffee")` at runtime  |
| `coffee.__version__`    | the same call, in `src/coffee/__init__.py`             |
| `make version`          | parsed out of `pyproject.toml`                          |
| this file               | kept in step by `make version-check`                    |

In a source checkout with no install, `coffee.__version__` falls back to
`0.0.0+dev` rather than guessing.

`make version-check` fails if the number above and the one in `pyproject.toml`
disagree. It runs as part of `make ci`, so the two cannot drift silently.

## Scheme

[Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html), with the
public API read as **the command-line surface and the rendered display**, not
the Python modules:

- **MAJOR** — a sub-command, flag or exit code is removed or changes meaning;
  the dashboard's layout changes in a way a user would notice.
- **MINOR** — a sub-command, flag or panel is added; behaviour changes in a way
  that is backwards compatible.
- **PATCH** — bug fixes, performance, documentation, internal refactoring.

While the version is `0.x`, MINOR carries the breaking changes that MAJOR
otherwise would.

The Python modules under `src/coffee/` are **not** a stable API. Import them at
your own risk; they are organised for the CLI's benefit and may be rearranged
in any MINOR release.

### What counts as a display change

The panels are the product, so they get SemVer treatment of their own:
`tests/test_parity.py` renders every panel and diffs the styled output against
a reference. A deliberate visual change means updating that reference in the
same commit and saying so in [CHANGELOG.md](CHANGELOG.md).

## Cutting a release

```sh
# 1. bump the number in pyproject.toml and in this file
# 2. move [Unreleased] in CHANGELOG.md under the new version and date it
make version-check    # the two numbers agree
make ci               # lint, compile, tests, smoke
make release          # test + build + tag + GitHub release
```

`make release` tags `v$(VERSION)`, pushes the tag, and publishes a GitHub
release with the wheel and sdist attached. The `release` workflow in
`.github/workflows/release.yml` does the same thing when a `v*` tag is pushed
by hand.

## History

See [CHANGELOG.md](CHANGELOG.md) for what changed in each release, and the
[releases page](https://github.com/bhaskarbhaumik/cli-coffee/releases) for the
built artefacts.
