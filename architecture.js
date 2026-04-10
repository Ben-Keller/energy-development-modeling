(function () {
  const SPEC_URL = './architecture.spec.json';
  const tooltip = document.getElementById('tooltip');
  const container = document.getElementById('diagram');
  const status = document.getElementById('status');
  const css = getComputedStyle(document.documentElement);

  function cssVar(name, fallback) {
    return (css.getPropertyValue(name).trim() || fallback);
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function listHtml(title, values, max = 4) {
    if (!Array.isArray(values) || values.length === 0) return '';
    return `<div class="tt-section">${escapeHtml(title)}</div><ul>${values.slice(0, max).map(v => `<li>${escapeHtml(v)}</li>`).join('')}</ul>`;
  }

  async function loadSpec() {
    const res = await fetch(SPEC_URL, { cache: 'no-store' });
    if (!res.ok) throw new Error(`Failed to load ${SPEC_URL}: ${res.status}`);
    return res.json();
  }

  function colorFor(spec, tone) {
    const themeColor = spec.theme && spec.theme.tones && spec.theme.tones[tone];
    return themeColor || cssVar(`--${tone}`, '#7f8698');
  }

  function applyTheme(spec) {
    const theme = spec.theme || {};
    const rootStyle = document.documentElement.style;
    [
      ['--bg', theme.background],
      ['--ink', theme.ink],
      ['--muted', theme.muted],
      ['--grid', theme.grid],
      ['--layer', theme.layer],
      ['--stroke', theme.stroke],
    ].forEach(([key, value]) => {
      if (value) rootStyle.setProperty(key, value);
    });
    Object.entries(theme.tones || {}).forEach(([tone, value]) => {
      rootStyle.setProperty(`--${tone}`, value);
    });
  }

  function rectsOverlap(a, b, pad) {
    return !(
      a.x + a.w + pad <= b.x ||
      b.x + b.w + pad <= a.x ||
      a.y + a.h + pad <= b.y ||
      b.y + b.h + pad <= a.y
    );
  }

  function prepareSpec(rawSpec) {
    const prepared = JSON.parse(JSON.stringify(rawSpec || {}));
    const nodes = prepared.nodes || [];
    const pad = prepared.rendering?.collisionPadding ?? 28;

    for (let pass = 0; pass < 10; pass += 1) {
      let moved = false;
      nodes.sort((a, b) => (a.y - b.y) || (a.x - b.x));
      for (let i = 0; i < nodes.length; i += 1) {
        for (let j = i + 1; j < nodes.length; j += 1) {
          const a = nodes[i];
          const b = nodes[j];
          if (!rectsOverlap(a, b, pad)) continue;
          const push = (a.y + a.h + pad) - b.y;
          b.y += Math.max(push, pad);
          moved = true;
        }
      }
      if (!moved) break;
    }

    const bottom = nodes.reduce((max, node) => Math.max(max, node.y + node.h), 0);
    const right = nodes.reduce((max, node) => Math.max(max, node.x + node.w), 0);
    prepared.rendering = prepared.rendering || {};
    prepared.rendering.height = Math.max(prepared.rendering.height || 0, bottom + 84);
    prepared.rendering.width = Math.max(prepared.rendering.width || 0, right + 80);
    return prepared;
  }

  function truncateText(value, maxChars) {
    const text = String(value || '');
    if (text.length <= maxChars) return text;
    return text.slice(0, Math.max(1, maxChars - 1)).trimEnd() + '...';
  }

  function wrapPlainText(value, maxChars) {
    const text = String(value || '').trim();
    if (!text) return [];
    const lines = [];
    let line = '';
    text.split(/\s+/).forEach((word) => {
      const candidate = line ? `${line} ${word}` : word;
      if (candidate.length > maxChars && line) {
        lines.push(line);
        line = word;
      } else {
        line = candidate;
      }
    });
    if (line) lines.push(line);
    return lines;
  }

  function draw(spec) {
    spec = prepareSpec(spec);
    applyTheme(spec);
    status.textContent = `${spec.title || 'Architecture'} · ${spec.schemaVersion || 'spec'}`;

    const palette = Object.fromEntries(
      Object.keys((spec.theme && spec.theme.tones) || {}).map(tone => [tone, colorFor(spec, tone)])
    );
    ['dataInput', 'model', 'output', 'quality', 'scenario', 'energy', 'bridge', 'mrio', 'impact', 'frontend', 'data'].forEach(tone => {
      if (!palette[tone]) palette[tone] = colorFor(spec, tone);
    });

    const width = spec.rendering?.width || spec.width || 1560;
    const height = spec.rendering?.height || spec.height || 1180;
    const svg = d3.select(container).append('svg').attr('role', 'img').attr('aria-label', spec.title || 'Architecture diagram');
    const defs = svg.append('defs');

    defs.append('filter')
      .attr('id', 'shadow')
      .attr('x', '-25%').attr('y', '-25%')
      .attr('width', '170%').attr('height', '180%')
      .html('<feDropShadow dx="0" dy="12" stdDeviation="16" flood-color="rgba(0,0,0,0.42)"/>');

    Object.entries(palette).forEach(([k, v]) => {
      defs.append('marker')
        .attr('id', 'arrow-' + k)
        .attr('viewBox', '0 0 12 12')
        .attr('refX', 10.5)
        .attr('refY', 6)
        .attr('markerWidth', 11)
        .attr('markerHeight', 11)
        .attr('orient', 'auto-start-reverse')
        .append('path')
        .attr('d', 'M0,0 L12,6 L0,12 z')
        .attr('fill', v);
    });

    const root = svg.append('g');
    const viewport = root.append('g');
    let currentTransform = d3.zoomIdentity;
    const zoomExtent = spec.rendering?.zoomExtent || [0.6, 1.8];

    const zoom = d3.zoom()
      .scaleExtent(zoomExtent)
      .on('zoom', (event) => {
        currentTransform = event.transform;
        viewport.attr('transform', currentTransform);
      });

    svg.call(zoom).on('dblclick.zoom', null);

    function wrapText(selection, width, lineHeight = 15) {
      selection.each(function() {
        const text = d3.select(this);
        const words = text.text().split(/\s+/).reverse();
        const x = text.attr('x');
        const y = text.attr('y');
        let word;
        let line = [];
        let lineNumber = 0;
        text.text(null);
        let tspan = text.append('tspan').attr('x', x).attr('y', y).attr('dy', '0px');
        while ((word = words.pop())) {
          line.push(word);
          tspan.text(line.join(' '));
          if (tspan.node().getComputedTextLength() > width && line.length > 1) {
            line.pop();
            tspan.text(line.join(' '));
            line = [word];
            tspan = text.append('tspan').attr('x', x).attr('y', y).attr('dy', (++lineNumber * lineHeight) + 'px').text(word);
          }
        }
      });
    }

    function nodeFill(d) {
      const c = d3.color(palette[d.tone] || '#7f8698');
      return d.light ? c.darker(0.35) : c.darker(0.85);
    }
    function nodeStroke(d) {
      const c = d3.color(palette[d.tone] || '#7f8698');
      return d.light ? c.brighter(0.4) : c.brighter(0.15);
    }

    function showTooltip(event, d, type = 'node') {
      const details = d.details || {};
      const title = type === 'edge' ? (d.label || 'Flow') : d.title;
      const sub = type === 'edge' ? 'Connector' : (d.subtitle || '');
      let html = `<div class="tt-title">${escapeHtml(title)}</div>`;
      if (sub) html += `<div class="tt-sub">${escapeHtml(sub)}</div>`;
      if (type === 'edge') {
        const edgeDetails = typeof d.details === 'object' ? d.details : { summary: d.details };
        if (edgeDetails.summary) html += `<div>${escapeHtml(edgeDetails.summary)}</div>`;
        html += listHtml('Payload', edgeDetails.payload, 5);
      } else {
        if (details.purpose) html += `<div>${escapeHtml(details.purpose)}</div>`;
        if (details.owner) html += `<div class="tt-section">Owner</div><div>${escapeHtml(details.owner)}</div>`;
        html += listHtml('Inputs', details.inputs, 4);
        html += listHtml('Outputs', details.outputs, 4);
        html += listHtml('Artifacts', details.artifacts, 4);
        html += listHtml('Acceptance criteria', details.acceptanceCriteria, 3);
        if (details.qualityPolicy) html += `<div class="tt-section">Quality policy</div><div>${escapeHtml(details.qualityPolicy)}</div>`;
      }
      tooltip.innerHTML = html;
      tooltip.classList.add('visible');
      moveTooltip(event);
    }

    function moveTooltip(event) {
      const rect = tooltip.getBoundingClientRect();
      let x = event.clientX + 18;
      let y = event.clientY + 18;
      if (x + rect.width > window.innerWidth - 12) x = event.clientX - rect.width - 18;
      if (y + rect.height > window.innerHeight - 12) y = event.clientY - rect.height - 18;
      tooltip.style.left = x + 'px';
      tooltip.style.top = y + 'px';
    }

    function hideTooltip() { tooltip.classList.remove('visible'); }

    function nodeAnchor(node, side) {
      if (side === 'bottom') return [node.x + node.w / 2, node.y + node.h];
      if (side === 'top') return [node.x + node.w / 2, node.y];
      if (side === 'left') return [node.x, node.y + node.h / 2];
      return [node.x + node.w, node.y + node.h / 2];
    }

    function route(edge, source, target) {
      const leftToRight = source.x < target.x;
      const sourceSide = leftToRight && Math.abs(source.y - target.y) < 180 ? 'right' : (source.y < target.y ? 'bottom' : 'top');
      const targetSide = leftToRight && Math.abs(source.y - target.y) < 180 ? 'left' : (source.y < target.y ? 'top' : 'bottom');
      const [sx, sy] = nodeAnchor(source, sourceSide);
      const [tx, ty] = nodeAnchor(target, targetSide);
      const mx = sx + (tx - sx) * 0.5;
      if (sourceSide === 'bottom' || sourceSide === 'top') {
        const midY = sy + (ty - sy) * 0.5;
        return `M${sx},${sy} L${sx},${midY} L${tx},${midY} L${tx},${ty}`;
      }
      return `M${sx},${sy} L${mx},${sy} L${mx},${ty} L${tx},${ty}`;
    }

    function edgeLabelPos(pathEl) {
      const len = pathEl.getTotalLength();
      return pathEl.getPointAtLength(len * 0.5);
    }

    function renderLegend() {
      const entries = Array.isArray(spec.legend) ? spec.legend : [];
      if (!entries.length) return;

      const cfg = spec.rendering?.legend || {};
      const legend = viewport.append('g')
        .attr('class', 'diagram-legend')
        .attr('transform', `translate(${cfg.x ?? 46},${cfg.y ?? 22})`);

      const title = cfg.title || 'Legend';
      legend.append('rect')
        .attr('class', 'legend-card')
        .attr('width', cfg.w || 560)
        .attr('height', cfg.h || 34)
        .attr('rx', 17);

      legend.append('text')
        .attr('class', 'legend-title')
        .attr('x', 14)
        .attr('y', 22)
        .text(title);

      let x = 122;
      entries.forEach(entry => {
        const color = palette[entry.tone] || '#7f8698';
        const label = entry.label || entry.tone || 'Entry';
        const labelWidth = Math.max(96, String(label).length * 7.4 + 36);
        const item = legend.append('g')
          .attr('class', 'legend-item')
          .attr('transform', `translate(${x},0)`)
          .on('mouseenter', (event) => {
            showTooltip(event, {
              title: label,
              subtitle: 'Legend item',
              details: {
                purpose: entry.description || label,
                owner: 'Architecture visual language'
              }
            });
          })
          .on('mousemove', moveTooltip)
          .on('mouseleave', hideTooltip);

        item.append('circle')
          .attr('cx', 10)
          .attr('cy', 17)
          .attr('r', 6)
          .attr('fill', color);
        item.append('text')
          .attr('class', 'legend-label')
          .attr('x', 22)
          .attr('y', 21)
          .text(label);
        x += labelWidth;
      });
    }

    function render() {
      svg.attr('viewBox', `0 0 ${width} ${height}`);
      viewport.selectAll('*').remove();

      viewport.append('g').selectAll('rect.layer-band')
        .data(spec.layers || [])
        .join('rect')
        .attr('class', 'layer-band')
        .attr('x', 34)
        .attr('y', d => d.y)
        .attr('width', width - 68)
        .attr('height', d => d.h)
        .attr('rx', spec.rendering?.layerCornerRadius || 22);

      viewport.append('g').selectAll('text.layer-title')
        .data(spec.layers || [])
        .join('text')
        .attr('class', 'layer-title')
        .attr('x', 46)
        .attr('y', d => d.y - 12)
        .text(d => d.title);

      const edgeGroup = viewport.append('g').attr('class', 'edges');
      const nodeById = new Map((spec.nodes || []).map(d => [d.id, d]));
      const validEdges = (spec.edges || []).filter(e => nodeById.has(e.from) && nodeById.has(e.to));

      const edges = edgeGroup.selectAll('g.edge-wrap')
        .data(validEdges)
        .join('g')
        .attr('class', 'edge-wrap');

      edges.append('path')
        .attr('class', 'edge')
        .attr('id', d => `edge-${d.id}`)
        .attr('d', d => route(d, nodeById.get(d.from), nodeById.get(d.to)))
        .attr('stroke', d => palette[d.tone] || '#7f8698')
        .attr('marker-end', d => `url(#arrow-${d.tone})`)
        .on('mouseenter', function(event, d) {
          d3.select(this).classed('active', true);
          showTooltip(event, d, 'edge');
        })
        .on('mousemove', moveTooltip)
        .on('mouseleave', function() { d3.select(this).classed('active', false); hideTooltip(); });

      if (spec.rendering?.showEdgeLabels !== false) {
        edges.each(function(d) {
          const p = d3.select(this).select('path').node();
          const pt = edgeLabelPos(p);
          const labelW = spec.rendering?.edgeLabelWidth || 156;
          const labelH = spec.rendering?.edgeLabelHeight || 20;
          d3.select(this).append('rect')
            .attr('x', pt.x - labelW / 2)
            .attr('y', pt.y - labelH / 2 - 2)
            .attr('width', labelW)
            .attr('height', labelH)
            .attr('rx', labelH / 2)
            .attr('fill', 'rgba(2,4,10,0.86)')
            .attr('stroke', 'rgba(255,255,255,0.12)');
          d3.select(this).append('text')
            .attr('class', 'edge-label')
            .attr('x', pt.x)
            .attr('y', pt.y)
            .attr('text-anchor', 'middle')
            .attr('dominant-baseline', 'middle')
            .text(d.label);
        });
      }

      viewport.append('g').selectAll('text.annotation')
        .data(spec.annotations || [])
        .join('text')
        .attr('class', 'annotation')
        .attr('x', d => d.x)
        .attr('y', d => d.y)
        .attr('text-anchor', 'middle')
        .attr('fill', d => palette[d.tone] || '#667085')
        .text(d => d.text);

      renderLegend();

      const nodes = viewport.append('g').attr('class', 'nodes')
        .selectAll('g.node')
        .data(spec.nodes || [])
        .join('g')
        .attr('class', d => `node${d.light ? ' light' : ''}`)
        .attr('transform', d => `translate(${d.x},${d.y})`)
        .call(d3.drag()
          .on('start', function() { d3.select(this).raise(); })
          .on('drag', function(event, d) {
            d.x += event.dx;
            d.y += event.dy;
            d3.select(this).attr('transform', `translate(${d.x},${d.y})`);
            edgeGroup.selectAll('path.edge').attr('d', e => route(e, nodeById.get(e.from), nodeById.get(e.to)));
            edgeGroup.selectAll('g.edge-wrap').each(function() {
              const p = d3.select(this).select('path').node();
              const pt = edgeLabelPos(p);
              const labelW = spec.rendering?.edgeLabelWidth || 156;
              const labelH = spec.rendering?.edgeLabelHeight || 20;
              d3.select(this).select('rect').attr('x', pt.x - labelW / 2).attr('y', pt.y - labelH / 2 - 2);
              d3.select(this).select('text').attr('x', pt.x).attr('y', pt.y);
            });
          })
        )
        .on('mouseenter', function(event, d) { d3.select(this).classed('active', true); showTooltip(event, d); })
        .on('mousemove', moveTooltip)
        .on('mouseleave', function() { d3.select(this).classed('active', false); hideTooltip(); });

      nodes.append('rect')
        .attr('class', 'card')
        .attr('width', d => d.w)
        .attr('height', d => d.h)
        .attr('rx', spec.rendering?.nodeCornerRadius || 18)
        .attr('fill', d => nodeFill(d))
        .attr('stroke', d => nodeStroke(d));

      nodes.append('text')
        .attr('class', 'subtitle')
        .attr('x', 22)
        .attr('y', 24)
        .text(d => d.subtitle || '');

      nodes.append('text')
        .attr('class', 'title')
        .attr('x', 22)
        .attr('y', d => d.subtitle ? 48 : 34)
        .text(d => truncateText(d.title, Math.floor((d.w - 44) / 8.4)));

      nodes.each(function(d) {
        const g = d3.select(this);
        const y0 = d.subtitle ? 68 : 54;
        const body = Array.isArray(d.body) ? d.body : [];
        const text = g.append('text').attr('class', 'body');
        const maxChars = Math.max(28, Math.floor((d.w - 54) / 6.5));
        const maxTextY = Math.max(y0, d.h - 54);
        let cursorY = y0;
        body.forEach((item) => {
          const lines = wrapPlainText('* ' + item, maxChars);
          lines.forEach((line) => {
            if (cursorY > maxTextY) return;
            text.append('tspan')
              .attr('x', 22)
              .attr('y', cursorY)
              .text(cursorY + 16 > maxTextY ? truncateText(line, maxChars - 3) : line);
            cursorY += 16;
          });
          cursorY += 3;
        });

        const chipsY = d.h - 28;
        let cx = 22;
        (d.chips || []).forEach(label => {
          const chipW = Math.max(74, String(label).length * 6.7 + 18);
          if (cx + chipW > d.w - 16) return;
          g.append('rect').attr('class', 'chip').attr('x', cx).attr('y', chipsY - 12).attr('width', chipW).attr('height', 22).attr('rx', 11);
          g.append('text').attr('class', 'chip-label').attr('x', cx + chipW / 2).attr('y', chipsY + 3).attr('text-anchor', 'middle').text(label);
          cx += chipW + 8;
        });

        if (d.ports) {
          d.ports.forEach(p => {
            g.append('text').attr('class', 'port-label').attr('x', p.x).attr('y', -8).text(p.label);
          });
        }
      });

      const bounds = viewport.node().getBBox();
      const fitPaddingRatio = spec.rendering?.fitPaddingRatio || 0.94;
      const availableWidth = Math.max(container.clientWidth || window.innerWidth || width, 1);
      const availableHeight = Math.max(container.clientHeight || window.innerHeight || height, 1);
      const rawScale = Math.min((availableWidth * fitPaddingRatio) / bounds.width, (availableHeight * fitPaddingRatio) / bounds.height);
      const scale = Number.isFinite(rawScale) && rawScale > 0 ? rawScale : 1;
      const tx = (availableWidth - bounds.width * scale) / 2 - bounds.x * scale;
      const ty = (availableHeight - bounds.height * scale) / 2 - bounds.y * scale;
      svg.call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
    }

    render();
    requestAnimationFrame(render);
    window.setTimeout(render, 120);
    window.addEventListener('resize', render);
  }

  loadSpec().then(draw).catch((err) => {
    console.error(err);
    status.textContent = `Failed to load architecture spec: ${err.message}`;
  });
})();
