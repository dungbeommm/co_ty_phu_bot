# Security

- Never commit `.env` or a Telegram token.
- Revoke exposed tokens immediately with `/revoke` in @BotFather.
- Store production tokens in the host secret manager.
- Do not run two long-polling instances with the same token.
