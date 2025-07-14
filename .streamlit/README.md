# Streamlit Configuration Guide

This directory contains Streamlit configuration files for optimal deployment and performance.

## Files Overview

### `config.toml` ✅ **Ready for Production**
Main configuration file with:
- **File Upload Limits**: 200MB for large Excel/PDF files
- **Memory Management**: Optimized for performance
- **Security Settings**: CORS, XSRF protection
- **Theme Settings**: Consistent UI appearance
- **Performance Tuning**: Caching and fast reruns

### `secrets.toml.template` 📋 **Template Only**
Template for sensitive configuration:
- Google Sheets URLs
- Admin passwords
- API keys
- Database credentials

### `credentials.toml` 🔧 **Optional**
Additional credentials for services like:
- AWS S3 (for file storage)
- Plotly configuration
- Mapbox tokens

## Deployment Instructions

### For Streamlit Cloud:
1. **Automatic Config**: `config.toml` is automatically used
2. **Add Secrets**: Copy values from `secrets.toml.template` to your app's Secrets section in Streamlit Cloud
3. **No Manual Setup**: Configuration is handled automatically

### For Heroku/Railway/Other Platforms:
1. **Config File**: The `config.toml` file is automatically loaded
2. **Environment Variables**: Set sensitive values as environment variables
3. **Port Configuration**: Uses `PORT` environment variable when available

### For Local Development:
1. **Copy Template**: Copy `secrets.toml.template` to `secrets.toml`
2. **Fill Real Values**: Replace template values with actual credentials
3. **Never Commit**: The `.gitignore` file prevents committing secrets

## Key Configuration Highlights

### Performance Optimizations:
- 🚀 **200MB file upload limit** for large Excel files
- 🔄 **Fast reruns enabled** for better UX
- 💾 **30-minute caching** for optimal performance
- 🎯 **Headless mode** for production

### Security Features:
- 🔒 **XSRF protection enabled**
- 🛡️ **CORS disabled** for security
- 📊 **Usage stats disabled** for privacy
- 🔐 **Secrets management** ready

### File Handling:
- 📁 **Large file support** up to 200MB
- 📊 **Excel/PDF optimized** for tools functionality
- 💽 **Memory-efficient** processing
- 🔄 **Streaming uploads** for better performance

## Troubleshooting

### File Upload Issues:
- Check `maxUploadSize` in `config.toml`
- Verify `maxMessageSize` setting
- Monitor memory usage

### Performance Issues:
- Adjust `maxCachedMessageAge`
- Check `fastReruns` setting
- Review `runOnSave` configuration

### Deployment Issues:
- Verify `headless = true` for production
- Check `port` configuration
- Validate `serverAddress` setting

## Environment Variables Override

You can override any config setting with environment variables:
```bash
STREAMLIT_SERVER_PORT=8080
STREAMLIT_SERVER_HEADLESS=true
STREAMLIT_SERVER_MAX_UPLOAD_SIZE=300
```

## Security Best Practices

1. ✅ **Never commit secrets.toml**
2. ✅ **Use environment variables in production**
3. ✅ **Keep config.toml in version control**
4. ✅ **Regularly update credentials**
5. ✅ **Monitor access logs**

---

*This configuration ensures your Mithila Tools Dashboard is optimized for both development and production deployment.*
