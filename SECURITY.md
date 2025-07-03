# Security Best Practices

## API Token Security

This project uses the SentinelOne API token, which should be handled securely:

1. **Never commit API tokens to the repository**
   - The `API_TOKEN` should only be stored as an environment variable or in GitHub Secrets
   - If you accidentally commit a token, consider it compromised and generate a new one

2. **For local development**
   - Set the token as an environment variable in your IDE or shell
   - For VSCode, use the `.env` file (already in `.gitignore`)
   - For command line: `export API_TOKEN=your_token_here`

3. **For production deployment**
   - Use GitHub Secrets with the name `SENTINEL_API_TOKEN`
   - For GitHub Codespaces, add `SENTINEL_API_TOKEN` as a Codespaces secret
   - For other CI/CD systems, use their respective secrets management

## Example `.env` file (for local development only)

```
API_TOKEN=your_token_here
BASE_URL=https://your-console.sentinelone.net/web/api/v2.1
```

Remember to add `.env` to your `.gitignore` file to prevent accidental commits.

## Security Considerations

- The API token has access to your SentinelOne management console and should be protected
- Consider using tokens with the minimum necessary permissions
- Regularly rotate your API tokens
- Monitor GitHub repository access to ensure only authorized users can access workflows with secrets
