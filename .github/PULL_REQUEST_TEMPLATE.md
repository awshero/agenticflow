## Jira Ticket
<!-- Link to Jira ticket -->
Ticket:
Summary:

## What Changed
<!-- Brief description of the changes -->


## Type of Change
- [ ] New feature
- [ ] Bug fix
- [ ] Refactor
- [ ] Documentation
- [ ] Tests only

## TDD Checklist
- [ ] Tests written FIRST (RED phase completed)
- [ ] All tests passing (GREEN phase completed)
- [ ] Code coverage >= 90%
- [ ] No linting errors (`flake8 src/ tests/`)

## Test Results
```
pytest tests/ -v --cov=src --cov-report=term-missing
```
<!-- Paste output here -->

## API Changes (if applicable)
| Endpoint | Method | Status Codes | Notes |
|----------|--------|--------------|-------|
| | | | |

## How to Test
```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Start API
uvicorn src.main:app --reload

# Test endpoint
curl http://localhost:8000/countries/France/capital
```

## Standards Compliance
- [ ] Follows API design standards
- [ ] Follows coding standards (type hints, naming, structure)
- [ ] Follows git standards (branch name, commit format)
- [ ] README-TEST-SCENARIOS.md updated

## Screenshots / API Response Examples
<!-- If applicable, show sample curl output -->

## Reviewer Notes
<!-- Anything specific you want the reviewer to focus on -->
