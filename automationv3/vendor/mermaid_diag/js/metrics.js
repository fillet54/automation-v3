/* Text measurement for dom_shim.js, in plain JavaScript.
 *
 * The page asks how big its text is through four hooks (__measureText, __measureTextFull, __measureGlyphs and
 * __measureForeignObject). They are answered here from fonts.json (globalThis.__MD_FONTS): the metrics of the
 * IBM Plex faces the diagrams are drawn with, so the sizes Mermaid lays out with are the sizes a browser draws.
 * Nothing calls back into the host, so the same code runs unchanged in QuickJS and in Node.
 *
 * A face is picked the way CSS does: the family from the font-family stack (Plex Sans, Mono or Serif), then
 * italic faces if italic is asked for and the family has any, then the nearest weight. Characters a Plex face
 * lacks are sized like the fallback fonts a browser would use: East Asian wide characters one em, emoji a little
 * wider, combining marks and joiners nothing.
 */
(function () {
  "use strict";

  const DATA = globalThis.__MD_FONTS;
  if (!DATA) throw new Error("metrics.js needs globalThis.__MD_FONTS (fonts.json)");

  function expand(runs) {
    const map = new Map();
    for (const [start, values] of runs) values.forEach((v, i) => map.set(start + i, v));
    return map;
  }

  const FACES = {};
  for (const [key, f] of Object.entries(DATA.faces)) {
    FACES[key] = {
      key, family: f.family, weight: f.weight, italic: f.italic,
      upm: f.unitsPerEm, ascent: f.ascent, descent: f.descent, lineGap: f.lineGap, xHeight: f.xHeight,
      notdef: f.notdef, adv: expand(f.advances), ink: expand(f.ink), kern: f.kerning,
    };
  }
  const WIDE = DATA.wide; // sorted [first, last] ranges

  globalThis.__MD_X_HEIGHT = FACES["sans-400"].xHeight / FACES["sans-400"].upm;

  // ---- face selection -------------------------------------------------------------------------------------

  function familyOf(stack) {
    for (const raw of String(stack == null ? "" : stack).split(",")) {
      const name = raw.replace(/["']/g, "").trim().toLowerCase();
      if (!name) continue;
      if (/mono|courier|consolas|menlo|monaco|monospace/.test(name)) return "mono";
      if (/serif|georgia|times|palatino|garamond/.test(name) && !/sans/.test(name)) return "serif";
      if (name) return "sans";
    }
    return "sans";
  }

  function weightOf(w) {
    const s = String(w == null ? "" : w).trim().toLowerCase();
    if (s === "bold" || s === "bolder") return 700;
    if (s === "lighter") return 300;
    const n = parseInt(s, 10);
    return Number.isNaN(n) ? 400 : n;
  }

  // CSS font matching (CSS Fonts 4, 5.2): style first, then weight.
  const faceCache = new Map();
  function pickFace(family, weight, style) {
    const fam = familyOf(family), want = weightOf(weight);
    const italic = /italic|oblique/.test(String(style || ""));
    const cacheKey = fam + "|" + want + "|" + italic;
    let face = faceCache.get(cacheKey);
    if (face) return face;
    let pool = Object.values(FACES).filter((f) => f.family === fam);
    if (italic && pool.some((f) => f.italic)) pool = pool.filter((f) => f.italic);
    else pool = pool.filter((f) => !f.italic);
    const weights = pool.map((f) => f.weight);
    let chosen;
    if (weights.includes(want)) chosen = want;
    else if (want >= 400 && want <= 500) {
      const up = weights.filter((w) => w > want && w <= 500).sort((a, b) => a - b);
      const down = weights.filter((w) => w < want).sort((a, b) => b - a);
      chosen = up[0] ?? down[0] ?? weights.filter((w) => w > 500).sort((a, b) => a - b)[0];
    } else if (want > 500) {
      const up = weights.filter((w) => w > want).sort((a, b) => a - b);
      chosen = up[0] ?? weights.filter((w) => w < want).sort((a, b) => b - a)[0];
    } else {
      const down = weights.filter((w) => w < want).sort((a, b) => b - a);
      chosen = down[0] ?? weights.filter((w) => w > want).sort((a, b) => a - b)[0];
    }
    face = pool.find((f) => f.weight === chosen) || FACES["sans-400"];
    faceCache.set(cacheKey, face);
    return face;
  }

  // ---- characters a Plex face lacks -------------------------------------------------------------------------

  function isWide(cp) {
    let lo = 0, hi = WIDE.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (cp < WIDE[mid][0]) hi = mid - 1;
      else if (cp > WIDE[mid][1]) lo = mid + 1;
      else return true;
    }
    return false;
  }

  function isZeroWidth(cp) {
    return (cp >= 0x0300 && cp <= 0x036F) || (cp >= 0x1AB0 && cp <= 0x1AFF) || (cp >= 0x20D0 && cp <= 0x20FF)
      || (cp >= 0x200B && cp <= 0x200F) || (cp >= 0x2060 && cp <= 0x2064) || (cp >= 0xFE00 && cp <= 0xFE0F)
      || (cp >= 0x1F3FB && cp <= 0x1F3FF) || (cp >= 0xE0020 && cp <= 0xE007F) || cp === 0xFEFF;
  }

  // Characters drawn from an emoji font by default (Unicode's Emoji_Presentation), as [first, last] ranges.
  const EMOJI = [[0x231A, 0x231B], [0x23E9, 0x23EC], [0x23F0, 0x23F0], [0x23F3, 0x23F3], [0x25FD, 0x25FE],
    [0x2614, 0x2615], [0x2648, 0x2653], [0x267F, 0x267F], [0x2693, 0x2693], [0x26A1, 0x26A1], [0x26AA, 0x26AB],
    [0x26BD, 0x26BE], [0x26C4, 0x26C5], [0x26CE, 0x26CE], [0x26D4, 0x26D4], [0x26EA, 0x26EA], [0x26F2, 0x26F3],
    [0x26F5, 0x26F5], [0x26FA, 0x26FA], [0x26FD, 0x26FD], [0x2705, 0x2705], [0x270A, 0x270B], [0x2728, 0x2728],
    [0x274C, 0x274C], [0x274E, 0x274E], [0x2753, 0x2755], [0x2757, 0x2757], [0x2795, 0x2797], [0x27B0, 0x27B0],
    [0x27BF, 0x27BF], [0x2B1B, 0x2B1C], [0x2B50, 0x2B50], [0x2B55, 0x2B55], [0x1F004, 0x1F004],
    [0x1F0CF, 0x1F0CF], [0x1F18E, 0x1F18E], [0x1F191, 0x1F19A], [0x1F1E6, 0x1F1FF], [0x1F201, 0x1F201],
    [0x1F21A, 0x1F21A], [0x1F22F, 0x1F22F], [0x1F232, 0x1F236], [0x1F238, 0x1F23A], [0x1F250, 0x1F251],
    [0x1F300, 0x1F64F], [0x1F680, 0x1F6FF], [0x1F7E0, 0x1F7F0], [0x1F90C, 0x1F9FF], [0x1FA70, 0x1FAFF]];
  function isEmoji(cp, nextCp) {
    if (nextCp === 0xFE0F) return true;      // the emoji variation selector: drawn as emoji
    for (const [a, b] of EMOJI) if (cp >= a && cp <= b) return true;
    return false;
  }

  const EMOJI_EM = 1.248;  // Noto Color Emoji's advance (Segoe UI Emoji's is close)
  const HANGUL_EM = 0.92;  // Hangul in Noto Sans CJK / Malgun Gothic
  const FALLBACK_EM = 0.6; // anything else: a typical sans glyph

  // Advance in font units of one character, and whether it carries ink.
  function advanceOf(face, cp, prevCp, nextCp, flagHalf) {
    if (nextCp === 0xFE0F && isEmoji(cp, nextCp)) return face.upm * EMOJI_EM;
    const a = face.adv.get(cp);
    if (a !== undefined) return a;
    if (isZeroWidth(cp)) return 0;
    if (prevCp === 0x200D) return 0;             // the second half of a joined emoji is drawn as one glyph
    if (flagHalf) return 0;                       // the second letter of a flag
    if (isEmoji(cp, nextCp)) return face.upm * EMOJI_EM;
    if ((cp >= 0xAC00 && cp <= 0xD7A3) || (cp >= 0x1100 && cp <= 0x11FF) || (cp >= 0x3130 && cp <= 0x318F)) {
      return face.upm * HANGUL_EM;
    }
    if (isWide(cp)) return face.upm;
    if (cp >= 0xFF61 && cp <= 0xFFDC) return face.upm / 2;   // half-width forms
    for (const other of [FACES["sans-400"], FACES["serif-400"], FACES["mono-400"]]) {
      const b = other.adv.get(cp);
      if (b !== undefined) return b * face.upm / other.upm;
    }
    return face.upm * FALLBACK_EM;
  }

  // Every character's pen position, in font units, with ASCII kerning applied.
  function walk(text, face) {
    const cps = Array.from(text == null ? "" : String(text), (ch) => ch.codePointAt(0));
    const glyphs = [];
    let pen = 0, prev = null, flagOpen = false;
    for (let i = 0; i < cps.length; i++) {
      const cp = cps[i], next = cps[i + 1];
      if (prev !== null && prev < 0x7F && cp < 0x7F) {
        const k = face.kern[prev + "," + cp];
        if (k !== undefined) pen += k;
      }
      const regional = cp >= 0x1F1E6 && cp <= 0x1F1FF;
      const flagHalf = regional && flagOpen;
      flagOpen = regional && !flagOpen;
      glyphs.push({ cp, pen, prev, next, flagHalf });
      pen += advanceOf(face, cp, prev, next, flagHalf);
      prev = cp;
    }
    return { glyphs, units: pen };
  }

  function measureFull(text, size, family, weight, style) {
    const face = pickFace(family, weight, style);
    const scale = (Number(size) || 16) / face.upm;
    return {
      width: walk(text, face).units * scale,
      ascent: face.ascent * scale,
      descent: face.descent * scale,
      xHeight: face.xHeight * scale,
    };
  }

  // [pen, ink left, ink right, ink top, ink bottom] in px for each character with ink.
  function measureGlyphs(text, size, family, weight, style) {
    const face = pickFace(family, weight, style);
    const scale = (Number(size) || 16) / face.upm;
    const boxes = [];
    for (const { cp, pen, prev, next, flagHalf } of walk(text, face).glyphs) {
      let ink = face.ink.get(cp);
      if (!ink && !face.adv.has(cp)) {
        const adv = advanceOf(face, cp, prev, next, flagHalf);
        if (adv > 0) ink = [0, adv, -face.ascent * 0.9, face.descent * 0.5];
      }
      if (ink) boxes.push([pen * scale, ink[0] * scale, ink[1] * scale, ink[2] * scale, ink[3] * scale]);
    }
    return boxes;
  }

  // ---- HTML labels (<foreignObject>) ----------------------------------------------------------------------------

  const ENTITIES = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };
  function decode(s) {
    return s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, e) => {
      if (e[0] === "#") {
        const cp = e[1] === "x" || e[1] === "X" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
        return Number.isFinite(cp) ? String.fromCodePoint(cp) : m;
      }
      return ENTITIES[e.toLowerCase()] ?? m;
    });
  }

  function styleProps(attrs) {
    const m = /\bstyle\s*=\s*("([^"]*)"|'([^']*)')/i.exec(attrs || "");
    const out = {};
    if (!m) return out;
    for (const part of decode(m[2] ?? m[3]).split(";")) {
      const i = part.indexOf(":");
      if (i > 0) out[part.slice(0, i).trim().toLowerCase()] = part.slice(i + 1).replace(/!important/i, "").trim();
    }
    return out;
  }

  function px(v, base) {
    const m = /^(-?\d*\.?\d+)(px|em|rem|%)?$/.exec(String(v || "").trim());
    if (!m) return null;
    const n = parseFloat(m[1]);
    if (m[2] === "em" || m[2] === "rem") return n * base;
    if (m[2] === "%") return n * base / 100;
    return n;
  }

  const BLOCKS = new Set(["p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote", "table", "tr"]);
  const VOID = new Set(["br", "img", "hr", "input", "wbr"]);

  // A computed line-height in px: unitless numbers scale with the element's own font size (and are inherited as
  // numbers), lengths are fixed, "normal" is the face's ascent + descent + line gap.
  function lineHeightPx(spec, size, face) {
    const s = String(spec == null ? "normal" : spec).trim();
    if (/^\d*\.?\d+$/.test(s)) return parseFloat(s) * size;
    const v = px(s, size);
    if (v != null) return v;
    return (face.ascent + face.descent + face.lineGap) / face.upm * size;
  }

  // The label's text as runs, [{text, face, size, spacing, lh, strut}], and {break} / {block} markers, plus the
  // outermost element's style (where Mermaid puts width, max-width and white-space). `style` carries the root's
  // font-style, text-transform, letter-spacing and line-height, ";"-separated (see dom_shim.js).
  function parseLabel(html, size, family, weight, style) {
    const items = [];
    const [fontStyle, transform, spacing, lineHeight] = String(style || "normal").split(";");
    const root = { tag: "", family, weight, style: fontStyle || "normal", size, transform: transform || "none",
                   spacing: spacing || "normal", lh: lineHeight || "normal", block: true };
    root.strut = lineHeightPx(root.lh, size, pickFace(family, weight, root.style));
    const stack = [root];
    let outer = null;
    const re = /<!--[\s\S]*?-->|<\/?([a-zA-Z][\w:-]*)([^>]*?)(\/?)>|([^<]+)/g;
    let m;
    while ((m = re.exec(html))) {
      const top = stack[stack.length - 1];
      if (m[4] !== undefined) {
        let text = decode(m[4]);
        if (top.transform === "uppercase") text = text.toUpperCase();
        else if (top.transform === "lowercase") text = text.toLowerCase();
        else if (top.transform === "capitalize") text = text.replace(/(^|\s)(\S)/g, (_, a, b) => a + b.toUpperCase());
        const face = pickFace(top.family, top.weight, top.style);
        const sp = top.spacing === "normal" ? 0 : (px(top.spacing, top.size) || 0);
        items.push({ text, face, size: top.size, spacing: sp, lh: lineHeightPx(top.lh, top.size, face), strut: top.strut });
        continue;
      }
      if (!m[1]) continue;
      const tag = m[1].toLowerCase().replace(/^.*:/, "");
      if (m[0][1] === "/") {
        for (let i = stack.length - 1; i > 0; i--) {
          if (stack[i].tag === tag) { stack.length = i; break; }
        }
        if (BLOCKS.has(tag)) items.push({ block: true });
        continue;
      }
      if (tag === "br") { items.push({ break: true, strut: top.strut }); continue; }
      const props = styleProps(m[2]);
      const isOuter = !outer;
      if (isOuter) outer = props;
      const block = isOuter || BLOCKS.has(tag) || /^(block|flex|table|list-item)/.test(props.display || "")
        && !/^inline/.test(props.display || "");
      if (block && !isOuter) items.push({ block: true });
      if (VOID.has(tag) || m[3] === "/") continue;
      const next = { tag, family: top.family, weight: top.weight, style: top.style, size: top.size,
                     transform: top.transform, spacing: top.spacing, lh: top.lh, strut: top.strut, block };
      if (tag === "b" || tag === "strong" || /^h[1-6]$/.test(tag)) next.weight = "700";
      if (tag === "i" || tag === "em" || tag === "cite" || tag === "var") next.style = "italic";
      if (tag === "code" || tag === "kbd" || tag === "samp" || tag === "tt" || tag === "pre") next.family = "monospace";
      if (props["font-family"]) next.family = props["font-family"];
      if (props["font-weight"]) next.weight = props["font-weight"];
      if (props["font-style"]) next.style = props["font-style"];
      if (props["font-size"]) next.size = px(props["font-size"], top.size) ?? top.size;
      if (props["text-transform"]) next.transform = props["text-transform"];
      if (props["letter-spacing"]) next.spacing = props["letter-spacing"];
      if (props["line-height"]) next.lh = props["line-height"];
      // A lone length is fixed: a child inherits the px value, not the expression.
      if (px(next.lh, next.size) != null && !/^\d*\.?\d+$/.test(String(next.lh).trim())) next.lh = px(next.lh, next.size) + "px";
      if (block) next.strut = lineHeightPx(next.lh, next.size, pickFace(next.family, next.weight, next.style));
      stack.push(next);
    }
    return { items, outer: outer || {} };
  }

  // Lays the label out as a browser would: words separated by spaces, broken onto lines when wrapping is on and
  // the next word would pass the available width. Each line is as tall as the taller of its block's line height
  // and the line heights of the text on it. Returns the widest line, the height and the number of lines.
  function layoutLabel(html, size, family, weight, style) {
    const base = Number(size) || 16;
    const { items, outer } = parseLabel(String(html || ""), base, family, weight, style);
    const ws = (outer["white-space"] || "normal").toLowerCase();
    const wraps = !(ws === "nowrap" || ws === "pre");
    const keepsSpaces = ws.startsWith("pre") || ws === "break-spaces";
    const limit = px(outer.width, base) ?? px(outer["max-width"], base);

    const lines = [];                     // [{width, height}]
    let line = 0, lineH = 0, pendingSpace = 0, word = 0, wordH = 0;
    let lineHasContent = false, wordHasContent = false, strut = 0;
    const endWord = () => {
      if (!wordHasContent) return;
      if (wraps && limit != null && lineHasContent && line + pendingSpace + word > limit + 0.01) {
        lines.push({ width: line, height: Math.max(lineH, strut) });
        line = word; lineH = wordH;
      } else {
        line += pendingSpace + word; lineH = Math.max(lineH, wordH);
      }
      pendingSpace = 0; word = 0; wordH = 0; wordHasContent = false; lineHasContent = true;
    };
    const breakLine = (force) => {
      endWord();
      if (lineHasContent || force) lines.push({ width: line, height: Math.max(lineH, strut) });
      line = 0; lineH = 0; pendingSpace = 0; lineHasContent = false;
    };

    for (const it of items) {
      if (it.break) { strut = it.strut; breakLine(true); continue; }
      if (it.block) { if (lineHasContent || wordHasContent) breakLine(false); continue; }
      strut = it.strut;
      let text = it.text;
      if (!keepsSpaces) text = text.replace(/[\t\n\r ]+/g, " ");
      const face = it.face, scale = it.size / face.upm, letter = it.spacing || 0;
      const spaceWidth = advanceOf(face, 0x20, null, null, false) * scale + letter;
      let piece = "";
      const flush = () => {
        if (piece) {
          // letter-spacing comes after every character
          word += walk(piece, face).units * scale + letter * Array.from(piece).length;
          wordH = Math.max(wordH, it.lh);
          wordHasContent = true; piece = "";
        }
      };
      for (const ch of text) {
        const cp = ch.codePointAt(0);
        if (ch === " " || (keepsSpaces && ch === "\t")) {
          flush(); endWord();
          if (lineHasContent || keepsSpaces) pendingSpace += spaceWidth;
        } else if (ch === "\n" && keepsSpaces) {
          flush(); breakLine(true);
        } else if (isWide(cp) && !face.adv.has(cp)) {
          flush(); endWord();            // East Asian text breaks between any two characters
          piece = ch; flush(); endWord();
        } else {
          piece += ch;
        }
      }
      flush();
    }
    endWord();
    if (lineHasContent) lines.push({ width: line, height: Math.max(lineH, strut) });
    if (!lines.length) lines.push({ width: 0, height: strut });

    const height = lines.reduce((sum, l) => sum + l.height, 0);
    return {
      width: Math.max(...lines.map((l) => l.width)),
      height,
      line_count: lines.length,
      line_height: lines[0].height,
    };
  }

  globalThis.__measureTextFull = measureFull;
  globalThis.__measureGlyphs = measureGlyphs;
  globalThis.__measureText = (t, s, f, w, st) => measureFull(t, s, f, w, st).width;
  globalThis.__measureForeignObject = layoutLabel;
  globalThis.__mdPickFace = (f, w, s) => pickFace(f, w, s).key;
})();
