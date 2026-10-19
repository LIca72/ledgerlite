# AI Usage Notes

## How I Used AI

I used ChatGPT to assist with implementation, debugging, testing, and refactoring.

I did not treat AI-generated code as a finished solution. I reviewed its suggestions, challenged unnecessary complexity, requested changes, and verified the results with tests and static analysis.

## Three AI Mistakes

1. **Overcomplicated views.** AI produced a views.py file exceeding 400 lines, with repeated authentication and error-handling logic. I pushed for refactoring, reducing it by approximately 120 lines.

2. **Missing imports.** During refactoring, AI removed imports still required by the transaction history endpoint. Ruff caught the errors, and we restored the imports.

3. **Broken refactoring script.** An AI-generated modification introduced an indentation error. I rejected that approach and continued with smaller, verifiable changes.

## My Decisions

I directed the implementation, reviewed architectural choices, and rejected solutions that added unnecessary complexity.

I relied on pytest and Ruff to validate changes rather than trusting AI-generated explanations.

AI helped me write code faster, but I remained responsible for evaluating the solutions and deciding what belonged in the project.

I was also perfectly willing to argue with AI when its suggestions made the code worse.

## Time Spent

Approximately 4 hours.
