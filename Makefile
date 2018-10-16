init:
	pipenv install

dev:
	pipenv install --dev

update:
	pipenv update

test:
	pipenv run py.test -v --exitfirst gymwipe

docs:
	pipenv run sphinx-apidoc --force --separate -o docs/api gymwipe gymwipe/test gymwipe/*/test
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
	# Open docs/_build/html/index.html to see the results

requirements:
	pipenv run pipenv_to_requirements
	cat requirements.txt | grep -v "#" >> requirements-dev.txt

.PHONY: init dev update test docs requirements