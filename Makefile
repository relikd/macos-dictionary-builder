all: dist

dist-env:
	@echo Creating virtual environment...
	@python3 -m venv 'dist-env'
	@source dist-env/bin/activate && pip install twine build

.PHONY: dist
dist: dist-env
	[ -z "$${VIRTUAL_ENV}" ]  # you can not do this inside a virtual environment.
	rm -rf dist
	@echo Building...
	@source dist-env/bin/activate && python3 -m build
	@echo
	rm -rf ./*.egg-info/
	@echo Publishing...
	@echo "\033[0;31mEnter your PyPI token:\033[0m"
	@source dist-env/bin/activate && export TWINE_USERNAME='__token__' && twine upload dist/*
