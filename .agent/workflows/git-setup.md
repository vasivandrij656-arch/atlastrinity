---
description: Configure Git user identity for commits
---

To ensure you can commit changes in this repository, run the appropriate setup command.

### 1. Token-based Remote Setup (Mandatory)

// turbo

```zsh
export GITHUB_TOKEN=$(grep GITHUB_TOKEN .env | cut -d'=' -f2 | tr -d '\r\n') && \
git remote set-url origin https://$GITHUB_TOKEN@github.com/vasivandrij656-arch/atlastrinity.git && \
echo "✅ Git remote configured with token from .env"
```

### 2. Set Identity

Configure your Git identity (name/email). If you are using an agent, use the agent's identity.

#### Antigravity Agent Identity

// turbo

```zsh
git config user.name "Antigravity AI"
git config user.email "antigravity-bot@google.com"
```

### 5. (Optional) Verify configuration

```zsh
git config --list | grep user
git remote -v
```

### 6. Manual Setup (If automation fails)

If Git still asks for login, run:

```zsh
git remote set-url origin https://<TOKEN>@github.com/vasivandrij656-arch/atlastrinity
```

_(Замініть `<TOKEN>` на значенння з вашого `.env`)_
