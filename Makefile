# uname will be linux if running on linux
UNAME := $(shell uname)

init:
	pipenv install

dev:
	pipenv install --dev

test:
	pipenv run py.test gymwipe

docs:
	pipenv run sphinx-apidoc -f -o docs/ gymwipe
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
	if [ $(UNAME) = Linux ]; then xdg-open docs/_build/html/index.html; fi

.PHONY: init dev test docs