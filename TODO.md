
This is a project which uses a Python [Claude Agent SDK](https://platform.claude.com/docs/en/agent-sdk/overview) agent to take as input:

1) Product metadata from a reference product detail page.

And outputs:

2) A script, shot list, any reference brand and product images, and other artifacts necessary to create a set of detailed prompts to create a storyboard of the proposed ad.

3) Uses these images and/or storyboard to create a Veo3-generated video short advertisement using FreePik's API: https://docs.freepik.com/introduction. The credentials should be stored in the environment in an .env file, which should never be committed to github. An env.example can be committed.

As a first milestone, we should close the loop to genereate a first video from input product detail page to output Veo3-generated video. We will then iterate on the closed loop to add generation of the intermediate artifacts as needed.

As a second phase of development, we should use either the [Yutori browsing API](https://docs.yutori.com/reference/browsing-create) or the [TinyFish API](https://docs.mino.ai/) to do the product research.