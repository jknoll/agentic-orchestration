# Deploying AdFlow to Vercel

This guide walks you through deploying AdFlow to Vercel for hosting the web interface and showcase.

## Important Note

**Vercel Serverless Limitations:** Vercel functions have a maximum execution timeout of 10-60 seconds (depending on plan). Full video generation typically takes 60+ seconds, so the deployed version runs in **demo mode** - it displays the interface and video showcase but cannot generate new videos.

For full video generation functionality, run the server locally or deploy to a platform that supports long-running processes (e.g., Railway, Render, or a VM).

## Prerequisites

- A GitHub account
- A Vercel account (free tier available)
- Your repository pushed to GitHub

## Step 1: Create a Vercel Account

1. Go to [vercel.com](https://vercel.com)
2. Click **Sign Up**
3. Choose **Continue with GitHub** (recommended for automatic deployments)
4. Authorize Vercel to access your GitHub account
5. Complete the onboarding flow

## Step 2: Import Your Project

1. From the Vercel dashboard, click **Add New...** > **Project**
2. Find your `agentic-orchestration` repository in the list
3. Click **Import**

## Step 3: Configure Build Settings

Vercel should auto-detect the project settings, but verify:

| Setting | Value |
|---------|-------|
| Framework Preset | Other |
| Root Directory | `./` |
| Build Command | (leave empty) |
| Output Directory | (leave empty) |
| Install Command | (leave empty) |

The project uses Vercel's Python runtime for serverless functions automatically.

## Step 4: Configure Environment Variables

Add the following environment variables in Vercel's project settings:

1. Go to **Settings** > **Environment Variables**
2. Add each variable:

| Variable | Required | Description |
|----------|----------|-------------|
| `FREEPIK_API_KEY` | Yes | FreePik API key for video generation |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for Claude |
| `KIE_API_KEY` | Optional | Kie.ai API key for Veo 3 |
| `MINO_API_KEY` | Optional | TinyFish/Mino API key for enhanced metadata |

### Getting API Keys

- **FreePik API Key**: Sign up at [freepik.com/api](https://www.freepik.com/api)
- **Anthropic API Key**: Get from [console.anthropic.com](https://console.anthropic.com)
- **Kie.ai API Key**: Register at [kie.ai](https://kie.ai/api-key)
- **Mino API Key**: Sign up at [app.mino.ai/signup](https://app.mino.ai/signup)

## Step 5: Deploy

1. Click **Deploy**
2. Wait for the build to complete (usually 1-2 minutes)
3. Your app will be available at `https://your-project.vercel.app`

## Step 6: Verify Deployment

Test the following endpoints:

```bash
# Health check
curl https://your-project.vercel.app/api/health

# Should return:
# {"status": "ok", "message": "AdFlow API running"}
```

Visit your deployment URL to see:
- Main interface at `/`
- Video showcase at `/video-showcase.html`

## Project Structure for Vercel

```
agentic-orchestration/
├── api/
│   └── index.py          # Serverless API function
├── frontend/
│   ├── index.html        # Main interface
│   └── video-showcase.html
├── output/               # Static video files
├── vercel.json           # Vercel configuration
└── ...
```

## Vercel Configuration

The `vercel.json` file configures API routing:

```json
{
  "rewrites": [
    { "source": "/api/:path*", "destination": "/api/index.py" }
  ]
}
```

## Automatic Deployments

Once connected to GitHub, Vercel automatically deploys:
- **Production**: When you push to `main` branch
- **Preview**: For every pull request

## Custom Domain (Optional)

1. Go to **Settings** > **Domains**
2. Add your custom domain
3. Follow DNS configuration instructions
4. SSL is automatically provisioned

## Troubleshooting

### Videos Not Loading

- Ensure video files are committed to the `output/` directory
- Check file paths in the showcase HTML
- Verify files aren't too large (Vercel has a 100MB file limit)

### API Timeout Errors

This is expected behavior. The demo mode returns immediately with a message explaining serverless limitations. For full functionality, run locally.

### Build Failures

- Check Vercel build logs for specific errors
- Ensure `requirements.txt` exists for Python dependencies
- Verify all required environment variables are set

### CORS Issues

The API includes CORS headers for all origins. If you encounter issues:
1. Check browser console for specific errors
2. Verify the API endpoint URL is correct
3. Test with `curl` to isolate browser-specific issues

## Running Locally vs Vercel

| Feature | Local | Vercel |
|---------|-------|--------|
| Web Interface | Yes | Yes |
| Video Showcase | Yes | Yes |
| Generate Videos | Yes | Demo only |
| Long-running Jobs | Yes | No (timeout) |
| Hot Reload | Yes | No |

## Support

- **Issues**: [GitHub Issues](https://github.com/jknoll/agentic-orchestration/issues)
- **Vercel Docs**: [vercel.com/docs](https://vercel.com/docs)
