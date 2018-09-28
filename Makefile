# uname will be linux if running on linux
UNAME := $(shell uname)

init:
	pipenv install

dev:
	pipenv install --dev

test:
	pipenv run py.test -v --exitfirst gymwipe

docs:
	pipenv run sphinx-apidoc --force --separate -o docs/api gymwipe gymwipe/test gymwipe/*/test
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
	# if [ $(UNAME) = Linux ]; then xdg-open docs/_build/html/index.html; fi

requirements:
	pipenv run pipenv_to_requirements
	cat requirements.txt | grep -v "#" >> requirements-dev.txt

.PHONY: init dev test docs requirements