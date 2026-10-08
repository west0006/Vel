# Lottie Creator MCP
undefined

## **Lottie Creator MCP**

The Lottie Creator MCP brings your AI assistant directly into your animation workflow — giving it full access to [LottieFiles Creator](https://creator.lottiefiles.com/) so it can build and edit Lottie animations on your behalf through natural language. You can check out the installation further down.

MCP servers are part of a standardized interface for AI agents to interact with data sources using the [Model Context Protocol](https://modelcontextprotocol.io/). The Lottie Creator MCP connects AI assistants like Claude, Cursor, and Windsurf to the Creator API through a local bridge — meaning your AI gets the same full access to Creator that you do.

**With the MCP enabled, you can:**

**✦ Create animations from scratch**

Describe what you want — a loading spinner, a progress bar, a character animation — and your AI will build it directly in Creator, layer by layer.

**✦ Edit and modify existing animations**

Change colors, adjust timing, swap easing curves, rename layers, or refactor an entire scene. Your AI reads the current state of your file and edits it in real time.

**✦ Batch generate animation variants**

Automatically produce multiple versions of an animation at once — dark and light themes, different sizes, brand color variations.

**✦ Analyze animations for accessibility and brand**

Ask your AI to inspect animations for contrast issues, motion speed, color consistency, or alignment with your brand guidelines — and fix what it finds.

**✦ Integrate into your project workflow**

Generate animation assets on the fly while working on a broader project.

To use the MCP, install it in your AI client and enable it in LottieFiles Creator. The sections below walk through each step.

## **Prerequisites**

Before installing, make sure you have the following set up:

✅ 📦 **Node.js 18+:** Required to run the MCP package via npx. [Download Node.js →](https://nodejs.org/)

✅ 🎬 **LottieFiles Creator:** Open [creator.lottiefiles.com](https://creator.lottiefiles.com/) in your browser and keep this tab open.

✅ 🤖 **An MCP-compatible AI:** Claude, Cursor, Windsurf, VS Code Copilot, or any other MCP-supporting assistant.

First, go to the [Creator MCP README file](https://www.npmjs.com/package/@lottiefiles/creator-mcp) where you can access the MCP strings and commands.

## Installing the MCP

For all of your AI tools, you can use the following config:

```jsx
{
  "mcpServers": {
    "lottiefiles-creator": {
      "command": "npx",
      "args": ["-y", "@lottiefiles/creator-mcp@latest"]
    }
  }
}
```

This documentation covers the installation steps for some of our supported MCP clients. For a list of install guides for supported MCP clients, see the list below:

## Supported MCP Clients

Follow the instructions for your specific client to install and connect the Lottie Creator MCP. Some clients also support skills, which add motion design knowledge so your AI can produce more intentional, polished animations. 🖇️ Here is the LottieFiles [motion design skill.](https://github.com/LottieFiles/motion-design-skill)

Follow the steps for your MCP client:

---

<Accordion type="single">
  <AccordionItem title="Claude Desktop" value="claude-desktop">
    **1. Open Claude Desktop Settings**

    Navigate to **Settings → Developer** and click **"Edit Config"**. This opens a JSON config file on your computer which you can edit in VS Code, Cursor, or any text editor.

    <Image src="https://assets.docs.lottiefiles.com/static/cbcf2779e6-640.webp" alt="Claude Desktop Settings → Developer, Edit Config" caption="Claude Desktop Settings" zoom variant="default" srcSet="https://assets.docs.lottiefiles.com/static/cbcf2779e6-640.webp 640w, https://assets.docs.lottiefiles.com/static/cbcf2779e6-1024.webp 1024w" width="1490" height="1070" loading="lazy" data-blur="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAGCAIAAABxZ0isAAAACXBIWXMAAAPoAAAD6AG1e1JrAAAAXklEQVR4nGWNSwqAMAxEc/8DiXgXF4rgp41pTNNWuxGpFEGYxcCbDwgjO5tPVaEUJZ9aBLtdinNkhFGFhPEBhOuVfA0G79DML6gL49B3bSOMMRxQin+B3Sb1+L0t4AYM8YjEckZSmwAAAABJRU5ErkJggg==" />

    **2. Add the MCP config**

    Paste the following into the config file inside the `mcpServers` object. You may need to add or remove brackets/commas to keep the JSON valid.

    ```jsx
    {
      "mcpServers": {
        "lottiefiles-creator": {
          "command": "npx",
          "args": ["-y", "@lottiefiles/creator-mcp@latest"]
        }
      }
    }
    ```

    Here's what the config file might look like after pasting the config above:

    ```jsx
    {
      "mcpServers": {
        "lottiefiles-creator": {
          "command": "npx",
          "args": ["-y", "@lottiefiles/creator-mcp@latest"]
        }
      },
      "preferences": {
        "quickEntryShortcut": "off",
        "coworkScheduledTasksEnabled": false,
        "ccdScheduledTasksEnabled": false,
        "sidebarMode": "chat",
        "coworkWebSearchEnabled": true,
        "floatingAtollActive": true
      }
    }
    ```

    **3. Verify it's connected**

    Click the **"+"** button in a chat, navigate to **Connectors**, and confirm the `lottiefiles-creator` toggle is on.

    <Image src="https://assets.docs.lottiefiles.com/static/661d017685-640.webp" alt="Claude Desktop Connectors with lottiefiles-creator enabled" zoom variant="default" srcSet="https://assets.docs.lottiefiles.com/static/661d017685-640.webp 640w, https://assets.docs.lottiefiles.com/static/661d017685-1024.webp 1024w" width="1470" height="840" loading="lazy" data-blur="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAFCAYAAAB4ka1VAAAACXBIWXMAABYlAAAWJQFJUiTwAAAAXUlEQVR4nE1NQQ7AIAjz/1/14CZGBJEu6JaMpGkobUmqioC7IybYfWGtgCEREUQEYzCuu6J1xZxnNzOkUgrMJoJzzhCdYO5QldNQiXZdJJh5i+eFvYYW4hH+h8/wAH2hnMwEoNxAAAAAAElFTkSuQmCC" />
  </AccordionItem>

  <AccordionItem title="Claude Code" value="claude-code">
    **1. Run the following command in your terminal**

    That's it. Claude Code will install and register the MCP automatically.

    ```
    claude mcp add lottiefiles-creator -- npx -y @lottiefiles/creator-mcp@latest
    ```
  </AccordionItem>

  <AccordionItem title="Cursor" value="cursor">
    #### **Using the Lottie Creator MCP for Cursor**

    1. Press `Cmd + Shift + P` (Mac) or `Ctrl + Shift + P` (Windows/Linux) → search **"Cursor Settings"**
    2. In the sidebar go to **Tools & MCPs**
    3. Click **"Add custom MCP"**

    <Image src="https://assets.docs.lottiefiles.com/static/1d779c5bf1-640.webp" alt="Cursor Settings → Tools & MCP, Add custom MCP" caption="Cursor Settings" zoom variant="default" srcSet="https://assets.docs.lottiefiles.com/static/1d779c5bf1-640.webp 640w, https://assets.docs.lottiefiles.com/static/1d779c5bf1-1024.webp 1024w" width="1724" height="1122" loading="lazy" data-blur="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAFCAYAAAB4ka1VAAAACXBIWXMAABYlAAAWJQFJUiTwAAAAYElEQVR4nD2OWQpFMQhDXUVnh1JKu/8N5qKPvg8hJPEoqSqYGbVWlFKQUkLO+T8kIhGOMXDvhZnFgpqGR27MOdF7j8JaC04VFbDyr/AoHuy9cc4JUmsN5BgXft9L75enP/5xNWNuTqnuAAAAAElFTkSuQmCC" />

    4. Paste in:

    ```jsx
    {
      "mcpServers": {
        "lottiefiles-creator": {
          "command": "npx",
          "args": ["-y", "@lottiefiles/creator-mcp@latest"]
        }
      }
    }
    ```

    Save and **fully restart Cursor** (quit and reopen - not just reload)

    After restart, go to **Settings → Tools & MCP** and you should see a green dot next to `lottiefiles-creator` confirming it's connected.

    <Image src="https://assets.docs.lottiefiles.com/static/d5e4c14c2c-640.webp" alt="Cursor Settings → Tools & MCP, lottiefiles-creator connected" zoom variant="default" srcSet="https://assets.docs.lottiefiles.com/static/d5e4c14c2c-640.webp 640w, https://assets.docs.lottiefiles.com/static/d5e4c14c2c-1024.webp 1024w" width="1724" height="1118" loading="lazy" data-blur="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAFCAYAAAB4ka1VAAAACXBIWXMAABYlAAAWJQFJUiTwAAAAYUlEQVR4nD2NSw7AIAhEOYVfBHSlsfe/3jTY2MUEeDAMqSpEBKUUpJQQQkCM8Rf5MucMZsacE713tNagZoeRmR3ow1oLY4xzICoQU5BHOKhcsZ/9fWCGG5sKyJ033+vtr14GGTV0KRWZBgAAAABJRU5ErkJggg==" />
  </AccordionItem>

  <AccordionItem title="VS Code" value="vs-code">
    **Option A: Deep link install**

    1. Click the [LottieFiles MCP server deep link.](https://vscode.dev/redirect/mcp/install?name=%40lottiefiles%2Fcreator-mcp\&config=%7B%22command%22%3A%22npx%22%2C%22args%22%3A%5B%22-y%22%2C%22%40lottiefiles%2Fcreator-mcp%22%5D%7D) This will open the MCP configuration in VS Code.
    2. Press the **Install** button.

    <Image src="https://assets.docs.lottiefiles.com/static/215df2a202-640.webp" alt="VS Code Install MCP Server prompt for Lottie Creator" zoom variant="default" srcSet="https://assets.docs.lottiefiles.com/static/215df2a202-640.webp 640w, https://assets.docs.lottiefiles.com/static/215df2a202-1024.webp 1024w" width="1720" height="736" loading="lazy" data-blur="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAADCAIAAAAhqtkfAAAACXBIWXMAAAPoAAAD6AG1e1JrAAAANUlEQVR4nGNQ19TW0NFX0tCSlVcQk5AUFBaFIAYJKRlxSSlhUXG4EFRCSkZOUlpWXFIKTQIAGEcGwVfSfA0AAAAASUVORK5CYII=" />

    **Option B: CLI or config file**

    Or via CLI:

    Terminal

    ```
    code --add-mcp '{"name":"lottiefiles-creator","command":"npx","args":["-y","@lottiefiles/creator-mcp@latest"]}'
    ```

    Or add to your `.vscode/mcp.json`:

    JSON — .vscode/mcp.json

    ```
    {
      "servers": {
        "lottiefiles-creator": {
          "command": "npx",
          "args": ["-y", "@lottiefiles/creator-mcp@latest"]
        }
      }
    }
    ```

    ℹ️ You'll need [GitHub Copilot](https://github.com/features/copilot) enabled on your account to use MCP tools in VS Code.
  </AccordionItem>

  <AccordionItem title="Amp" value="amp">
    ```
    amp mcp add lottiefiles-creator -- npx -y @lottiefiles/creator-mcp@latest
    ```
  </AccordionItem>

  <AccordionItem title="Antigravity" value="antigravity">
    Follow Antigravity's MCP setup docs and use the config above.
  </AccordionItem>

  <AccordionItem title="Cline" value="cline">
    Follow Cline's MCP setup docs and use the config above.
  </AccordionItem>

  <AccordionItem title="Codex" value="codex">
    Follow the [configure MCP guide](https://github.com/openai/codex/blob/main/docs/config.md) using:

    ```
    [mcp_servers.lottiefiles-creator]
    command = "npx"
    args = ["-y", "@lottiefiles/creator-mcp@latest"]
    ```

    Or add via CLI:

    ```
    codex mcp add lottiefiles-creator -- npx -y @lottiefiles/creator-mcp@latest
    ```
  </AccordionItem>

  <AccordionItem title="Copilot CLI" value="copilot-cli">
    1. Start `copilot`
    2. Run `/mcp add`
    3. Configure:
       - Server name: `lottiefiles-creator`
       - Server type: `Local`
       - Command: `npx -y @lottiefiles/creator-mcp@latest`
  </AccordionItem>

  <AccordionItem title="Copilot / VS Code" value="copilot-vscode">
    Follow VS Code MCP setup docs and use the config above. Or via CLI:

    ```
    code --add-mcp '{"name":"lottiefiles-creator","command":"npx","args":["-y","@lottiefiles/creator-mcp@latest"]}'
    ```
  </AccordionItem>

  <AccordionItem title="Copilot / GitHub CLI" value="copilot-github-cli">
    ```
    gh copilot mcp add lottiefiles-creator -- npx -y @lottiefiles/creator-mcp@latest
    ```
  </AccordionItem>

  <AccordionItem title="Factory CLI" value="factory-cli">
    ```
    droid mcp add lottiefiles-creator "npx -y @lottiefiles/creator-mcp@latest"
    ```
  </AccordionItem>

  <AccordionItem title="Gemini CLI" value="gemini-cli">
    ```
    gemini mcp add lottiefiles-creator npx -y @lottiefiles/creator-mcp@latest
    gemini mcp add -s user lottiefiles-creator npx -y @lottiefiles/creator-mcp@latest
    ```
  </AccordionItem>

  <AccordionItem title="Gemini Code Assist" value="gemini-code-assist">
    Follow Gemini Code Assist MCP setup docs and use the config above.
  </AccordionItem>

  <AccordionItem title="JetBrains AI Assistant & Junie" value="jetbrains">
    Follow JetBrains MCP setup docs and use the config above.
  </AccordionItem>

  <AccordionItem title="Kiro" value="kiro">
    Follow Kiro MCP setup docs and use the config above.
  </AccordionItem>

  <AccordionItem title="Qoder" value="qoder">
    Follow Qoder MCP setup docs and use the config above.
  </AccordionItem>

  <AccordionItem title="Visual Studio" value="visual-studio">
    Add a local MCP server with:

    - Name: `lottiefiles-creator`
    - Command: `npx`
    - Arguments: `y @lottiefiles/creator-mcp@latest`
  </AccordionItem>

  <AccordionItem title="Warp" value="warp">
    Follow Warp MCP setup docs and use the config above.
  </AccordionItem>

  <AccordionItem title="Windsurf" value="windsurf">
    Follow Windsurf MCP setup docs and use the config above.
  </AccordionItem>
</Accordion>

## Connecting to Lottie Creator

1. **Open Lottie Creator**

Navigate to [creator.lottiefiles.com](https://creator.lottiefiles.com/) in your browser and keep this tab open throughout your session. The MCP communicates with Creator through this browser tab.

1. **Enable MCP in Creator**

In Creator, go to **Settings → MCP Settings → Enable MCP**.

<Image src="https://assets.docs.lottiefiles.com/static/159e2b8796-640.webp" alt="Lottie Creator Settings → MCP Settings with Enable MCP" zoom variant="default" srcSet="https://assets.docs.lottiefiles.com/static/159e2b8796-640.webp 640w, https://assets.docs.lottiefiles.com/static/159e2b8796-1024.webp 1024w" width="1254" height="968" loading="lazy" data-blur="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAGCAIAAABxZ0isAAAACXBIWXMAAAPoAAAD6AG1e1JrAAAAa0lEQVR4nF3MsQqEMBCE4X3/d7GytPAxLDyQ4woRc2vYdU0mGj2IXOPX/QwMDe+PFjFGACklAGZG3vsQgpldfznndYskIlvxHJhZVZnZOScid8pqNH95dn6clrM49gOAWqCuf1VNU7ft4+oHaRSI49LyMUwAAAAASUVORK5CYII=" />

1. **Confirm the connection**

You should see a notification in Creator: Local MCP bridge connected

<Image src="https://assets.docs.lottiefiles.com/static/d3eb3dcdd1-640.webp" alt="Lottie Creator notification: Local MCP bridge connected" zoom variant="default" srcSet="https://assets.docs.lottiefiles.com/static/d3eb3dcdd1-640.webp 640w, https://assets.docs.lottiefiles.com/static/d3eb3dcdd1-1024.webp 1024w, https://assets.docs.lottiefiles.com/static/d3eb3dcdd1-1920.webp 1920w" width="2400" height="1348" loading="lazy" data-blur="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAECAYAAACzzX7wAAAACXBIWXMAACxLAAAsSwGlPZapAAAARklEQVR4nGPwiUj+D8K+Uan//aLTwBjEhokzgCUjU/87+4X/t3H1/W/j6vffxS8CLIahwNbN77+dm/9/F3+QghSEAnxWAABJ2T+yIYIwhwAAAABJRU5ErkJggg==" />

If you see this, you're all set and ready to start prompting! Keep in mind, the animation quality heavily depends on which model you are using, so be sure to use the best model available to you.

<Image src="https://assets.docs.lottiefiles.com/static/95c94c80ec-640.webp" alt="Lottie Creator top bar with a blue MCP connection indicator next to the file name" zoom variant="default" srcSet="https://assets.docs.lottiefiles.com/static/95c94c80ec-640.webp 640w, https://assets.docs.lottiefiles.com/static/95c94c80ec-1024.webp 1024w, https://assets.docs.lottiefiles.com/static/95c94c80ec-1920.webp 1920w" width="2400" height="1348" loading="lazy" data-blur="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAECAYAAACzzX7wAAAACXBIWXMAACxLAAAsSwGlPZapAAAAWElEQVR4nF2NywqAIBRE/a9S25gPSK+6Stf5/38wcS0IWpyB4QyMOM4LsY+HNpCYt7MTJndIS1gtQfsC5QuWPUE6gqEGwaFcnmyhQoc6x9znIP4v+nfB7gb+KT6SlX5howAAAABJRU5ErkJggg==" />

## About Skills

Skills provide guidance for how an agent should approach animation tasks — using a combination of MCP tool calls and deep motion design knowledge baked in as reusable instructions.

While the Lottie Creator MCP exposes individual tools (create a layer, set a keyframe, adjust a fill), Skills help your AI understand _how to use them well_. Things like knowing which easing curve fits a bounce vs. a fade, how to sequence a multi-element entrance, or how to structure timing so an animation feels intentional rather than mechanical.

Skills don't replace the MCP connection or add new tools. They reduce guesswork by packaging motion design expertise into instructions your AI draws on automatically whenever it works on animations.

### Install the motion design skill

Run this command once in your terminal. It works with 40+ agents including Claude Code, Cursor, Codex, and GitHub Copilot.

Terminal

```
npx skills add LottieFiles/motion-design-skill
```

✨ **Highly recommended.** The difference between an AI that produces stiff, mechanical animations and one that produces polished, intentional motion is almost entirely down to whether it has this context. Install it once and it applies to every animation session.

View the full skill on GitHub → [LottieFiles/motion-design-skill](https://github.com/LottieFiles/motion-design-skill)

## Capabilities

The MCP gives your AI full access to the Creator API. Here's everything it can do:

**🎬 Scene Management**

- Create scenes — set name, size, framerate, duration
- Switch between scenes
- Set background color (preview only, not exported)
- Read scene properties — layers, size, framerate
- Export scenes to Lottie JSON
- Import Lottie JSON, dotLottie, SVG, or images

**🗂 Layer Management**

- Set visibility, lock state, and focus
- Control timing — start frame, end frame, offset
- Set blend modes (16 modes including multiply, screen, overlay)
- Apply and animate masks and mattes
- Align and flip layers
- Animate transforms — position, rotation, scale, skew

**🔷 Shape Creation**

- Rectangle — position, size, corner roundness
- Ellipse — position, size
- Polygon — points, radius, roundness
- Star — inner/outer radius, points
- Path — custom bezier with full tangent control
- Group — group existing shapes together

**🎨 Fills & Strokes**

- Solid color fill — static or animated RGB
- Linear gradient fill — custom start/end points
- Radial gradient fill — highlight angle and length
- Solid and gradient strokes — with animatable width
- Trim paths — animate drawing (start %, end %, offset)

**⏱️ Animation & Keyframes**

- Add keyframes at specific frames with values
- Set static values (no animation)
- Read, inspect, and remove keyframes
- Set easing — Linear or Cubic Bezier (x1, y1, x2, y2)
- Animate: position, rotation, scale, opacity, color, path, and more

**🖼 Asset & Playback**

- List, clone, and remove assets (scenes and images)
- Read image properties — width, height, base64 URI
- Play, pause, and jump to specific frames
- Read current frame and playback state
- Read selected nodes and keyframes

_Coming soon: State Machines and Motion Tokens_

## Best practices

- **Install the motion design skill for better quality:** The MCP gives your AI the tools. The motion design skill gives it the judgment to use them well — easing curves, timing principles, choreography. One command, significantly better output. Motion design skill can be found [here](https://lottie.link/motion-design-skill).
- **Start with your own SVGs, then animate:** AI can be unpredictable when generating illustration shapes from scratch. For the best results, import your existing SVG assets into Creator first, then ask your AI to animate them. This keeps your visual style consistent and lets the AI focus on what it does best — motion, timing, and sequencing.
  - Test out these remix links
    - Medal: [https://lottie.link/metal](https://lottie.link/metal)
    - Weather: [https://lottie.link/weather](https://lottie.link/weather)
    - Graph: [https://lottie.link/graph](https://lottie.link/graph)
    - Mail box: [https://lottie.link/mailbox1](https://lottie.link/mailbox1)
- **Always use the best model available to you:** Animation quality scales directly with the model. If you have access to Claude Sonnet or Opus, use it over a smaller model — the difference in how it handles timing, sequencing, and spatial reasoning is noticeable.
- **Name your layers before you prompt:** The AI reads your layer names to understand your animation's structure. Well-named layers like `left_arm`, `right_leg`, `bg_circle`, and `text_headline` help it target the right elements, avoid mistakes, and stay organized across complex scenes. Generic names like `Shape 1` or `Group 4` make it harder for the AI to build on your work accurately.
- **Break complex animations into steps:** Instead of "build me a full onboarding animation," go scene by scene. Create the scene → add shapes → add keyframes → refine timing. Smaller steps give you more control and make errors easier to catch and correct.
- **Be specific about timing and feel:** "A smooth fade" is vague. "A 400ms fade-in with ease-out" gives your AI something to work with. The more you describe the feel — snappy, bouncy, slow and cinematic — the closer the first result will be to what you're imagining.
