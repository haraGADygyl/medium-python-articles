# Diagram and cover sources — article 010

Diagrams are Mermaid (`*.mmd`). Render with:

```bash
echo '{"args":["--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage"]}' > pconf.json
npx -y @mermaid-js/mermaid-cli -i 01-race.mmd -o 01-race.png -b white -p pconf.json
```

The `--no-sandbox` config is required here; Puppeteer's bundled Chrome will not
launch without it.

The cover is plain HTML (`00-cover.html`), rendered at Medium's 1500x750 with:

```bash
google-chrome --headless --disable-gpu --no-sandbox --disable-dev-shm-usage \
  --hide-scrollbars --window-size=1500,750 \
  --screenshot=00-cover.png "file://$PWD/00-cover.html"
```

It uses only system fonts (Liberation Sans / DejaVu Sans Mono) so it renders
identically without network access.
