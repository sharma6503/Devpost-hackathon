# 🧹 Code Quality Standards

## 1. Maintainability
- **Function Length:** Functions should ideally not exceed 50 lines. Large functions should be refactored.
- **Complexity:** Avoid deep nesting (more than 3 levels). Use early returns.
- **Naming:** Variables and functions must have descriptive, snake_case names in Python.

## 2. Robustness
- **Error Handling:** Don't use bare `except:`. Always catch specific exceptions.
- **Validation:** Type hint public APIs and validate inputs early.

# 🔒 Security Standards

## 1. Data Protection
- **Secrets:** Never hardcode API keys, tokens, or passwords. Use environment variables.
- **Injection:** Always use parameterized queries for SQL or command execution.

## 2. Infrastructure
- **Permissions:** Follow the principle of least privilege.
- **Dependencies:** Avoid using deprecated or insecure libraries.
