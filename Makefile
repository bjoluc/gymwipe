# uname will be linux if running on linux
UNAME := $(shell uname)

init:
	pipenv install

test:
	pipenv run py.test gymwirelesscontrol

docs:
	pipenv run sphinx-apidoc -f -o docs/ gymwirelesscontrol
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
	if [ $(UNAME) = Linux ]; then xdg-open docs/_build/html/index.html; fi

.PHONY: init test docs