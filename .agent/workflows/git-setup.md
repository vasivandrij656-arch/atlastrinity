---
description: Configure Git user identity for commits
---

To ensure you can commit changes in this repository, run the appropriate setup command.

### 1. Automatic Setup (Recommended)
// turbo
```zsh
export GITHUB_TOKEN=$(grep GITHUB_TOKEN .env | cut -d'=' -f2) && \
git remote set-url origin https://$GITHUB_TOKEN@github.com/solagurma/atlastrinity.git && \
echo "✅ Git remote configured with token from .env"
```

### 2. Developer Identity (Kizyma Oleg)
// turbo
```zsh
git config user.name "Kizyma Oleg"
git config user.email "oleg1203@gmail.com"
```

### 3. Antigravity Agent Identity
// turbo
```zsh
git config user.name "Antigravity AI"
git config user.email "antigravity-bot@google.com"
```

### 4. Windsurf Agent Identity
// turbo
```zsh
git config user.name "Windsurf AI"
git config user.email "windsurf-bot@codeium.com"
```

### 5. (Optional) Verify configuration
```zsh
git config --list | grep user
git remote -v
```

### 6. Manual Setup (If automation fails)
If Git still asks for login, run:
```zsh
git remote set-url origin https://<TOKEN>@github.com/solagurma/atlastrinity
```
*(Замініть `<TOKEN>` на значенння з вашого `.env`)*
