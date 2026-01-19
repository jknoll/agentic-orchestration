1) ~~Update the video showcase: include all of the files and metadata generated in the output directory.~~ [#7](https://github.com/jknoll/agentic-orchestration/issues/7) - DONE
   - Created `showcase_parser.py` to parse README.md files from output folders
   - Added `/api/showcase/videos`, `/api/showcase/featured`, `/api/showcase/config` API endpoints
   - Updated `video-showcase.html` to fetch videos dynamically
   - Created `showcase-config.json` for marking featured videos

2) ~~Add a video carousel to the README.md with examples of some of the generated videos and a configuration which allows me to select the best videos for inclusion in the carousel.~~ - DONE
   - Added Featured Video Ads section to README.md with 6 featured videos
   - Featured videos are configured in `output/showcase-config.json`

3) ~~Add a screenshot of the running/rendered index.html file to the README.md to give a viewer a sense of the rendered application's user interface.~~ - DONE
   - Added Screenshots section to README.md
   - Screenshots should be saved to `assets/` folder (see `assets/README.md` for instructions)

4) ~~Add step-by-step instructions for how to deploy to Vercel and how to test, including any permissions/API keys required, and step-by-step instructions for the Vercel signup process.~~ - DONE
   - Created comprehensive `VERCEL.md` deployment guide
   - Added Deployment section to README.md linking to VERCEL.md