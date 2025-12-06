.PHONY: deps test typecheck

deps:
	npm install

test: typecheck
	npm test

typecheck:
	npm run typecheck
