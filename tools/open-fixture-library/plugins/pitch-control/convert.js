/**
 * @fileoverview
 * Open Fixture Library (OFL) fixture JSON → the channel modes of a PitchControl fixture type.
 *
 * This is a line-by-line port of PitchControl's own converter, `backend/src/pitchcontrol/ofl/convert.py`
 * (the one behind File → Import Fixture → Open Fixture Library in the app). A fixture exported by this plugin
 * must be the same file the app makes from the same fixture, so keep the two in step; see README.md.
 *
 * The mapping:
 * - every OFL mode becomes a channel mode with its own pixel count (the number of pixels or pixel groups its matrix block repeats for; 1 for a mode without one);
 * - colour channels that form R G B (W) become the `pixels` block, per pixel when OFL repeats them over a matrix; a warm or cold white counts as W;
 * - a strobe / shutter channel becomes `shutter`, with the open value and the fastest plain strobe value read from its capabilities;
 * - the master dimmer is held at 255 when the mode mixes colours itself, an `I` pixel (it follows the brightness) when the mode has no colour channels;
 * - everything else (amber, UV, programs, speed, sound, delay, mode select, fine channels) is a named constant at its OFL default value, 0 unless OFL says otherwise; a colour preset that is a mode's only colour source is held at its "White" preset;
 * - a channel that switches meaning with another channel (OFL "switching channels") is read with the controlling channel at its default value.
 *
 * A mode PitchControl can't express (a dimmer, amber or strobe per pixel, the pixels interleaved with other channels,
 * a hue / CCT / effect layout without a plain colour block) is not converted; `convertFixture` lists it with the
 * reason in `skipped`.
 */

/* eslint-disable camelcase -- the keys of PitchControl's file format are snake_case */

/** A white channel next to RGB is the W of an RGBW block. */
const WHITES = new Set(['White', 'Warm White', 'Cold White']);
const FORMATS = new Map([
  ['Red|Green|Blue|White', 'RGBW'],
  ['Red|Green|Blue', 'RGB'],
]);
const PIXEL_KEY = '$pixelKey';
/** How deep a matrix's `pixelKeys` are nested: planes, rows, keys. */
const PIXEL_KEYS_DEPTH = 2;

/** A mode (or a whole fixture) that can't be expressed as a PitchControl channel mode. */
export class ConversionError extends Error {
  /**
   * @param {string} message - Why the mode can't be expressed.
   */
  constructor(message) {
    super(message);
    this.name = 'ConversionError';
  }
}

/**
 * @typedef {object} Ref A channel of a mode, resolved against the fixture's availableChannels and templateChannels.
 * @property {string} name What the mode lists.
 * @property {object} definition The OFL channel definition.
 * @property {boolean} [fine] Whether it is the 16-bit fine half of another channel.
 * @property {boolean} [unused] Whether it is a switching channel that does nothing with the controlling channel at its default.
 */

/**
 * @typedef {object} Item
 * @property {'colour' | 'dimmer' | 'shutter' | 'const'} kind What the channel is for PitchControl.
 * @property {Ref} ref The channel.
 * @property {string} [colour] The colour of a colour channel.
 */

/**
 * @typedef {object} Block
 * @property {string[]} keys The pixels (or pixel groups) the template channels repeat for.
 * @property {Item[]} items The channels of one pixel.
 */

/**
 * @typedef {object} Converted
 * @property {object[]} modes The converted channel modes, in OFL's order.
 * @property {[string, string][]} skipped The OFL modes that couldn't be converted, with the reason.
 */

// --------------------------------------------------------------------------- the OFL side

/**
 * Python's `round`: halves go to the even number.
 * @param {number} value - The number to round.
 * @returns {number} The rounded integer.
 */
function roundHalfEven(value) {
  const floor = Math.floor(value);
  const fraction = value - floor;
  if (fraction < 0.5) {
    return floor;
  }
  if (fraction > 0.5) {
    return floor + 1;
  }
  return floor % 2 === 0 ? floor : floor + 1;
}

/**
 * @param {string} text - Any text.
 * @returns {string} The text as a literal inside a regular expression.
 */
function escapeRegExp(text) {
  return text.replaceAll(/[$()*+.?[\\\]^{|}]/g, String.raw`\$&`);
}

/**
 * @param {object} definition - An OFL channel definition.
 * @returns {object[]} Its capabilities (a channel with one capability has `capability`, not `capabilities`).
 */
function capabilitiesOf(definition) {
  return definition.capabilities ?? [definition.capability];
}

/**
 * @param {object} definition - An OFL channel definition.
 * @returns {boolean} Whether the channel has fine channels and its DMX values are 16-bit.
 */
function is16Bit(definition) {
  return Array.isArray(definition.fineChannelAliases) && definition.fineChannelAliases.length > 0 && definition.dmxValueResolution !== '8bit';
}

/**
 * @param {object} definition - An OFL channel definition.
 * @returns {{start: number, end: number, capability: object}[]} The capabilities with their DMX range in 8-bit values (16-bit channels are cut to their coarse byte).
 */
function ranges8(definition) {
  const isWide = is16Bit(definition);
  const top = isWide ? 65_535 : 255;
  return capabilitiesOf(definition).map((capability) => {
    const [start, end] = capability.dmxRange ?? [0, top];
    return isWide ? { start: Math.floor(start / 256), end: Math.floor(end / 256), capability } : { start, end, capability };
  });
}

/**
 * @param {object} definition - An OFL channel definition.
 * @returns {number} The channel's OFL default as an 8-bit value (0 when OFL gives none).
 */
function defaultValue(definition) {
  const value = 'defaultValue' in definition ? definition.defaultValue : 0;
  if (typeof value === 'string') { // "50%"
    return roundHalfEven(Number(value.replace(/%+$/, '')) * 2.55);
  }
  return is16Bit(definition) ? Math.floor(value / 256) : value;
}

/** One OFL fixture: channel lookup (plain, fine, template, switching) and the matrix. */
class FixtureData {
  /**
   * @param {object} data - The OFL fixture JSON.
   */
  constructor(data) {
    this.channels = data.availableChannels ?? {};
    this.templates = data.templateChannels ?? {};
    this.matrix = data.matrix ?? {};

    /** @type {Map<string, object>} fine channel alias → the definition it belongs to */
    this.fineOf = new Map();
    const pools = [this.channels, this.templates];
    for (const pool of pools) {
      const definitions = Object.values(pool);
      for (const definition of definitions) {
        const aliases = definition.fineChannelAliases ?? [];
        for (const alias of aliases) {
          this.fineOf.set(alias, definition);
        }
      }
    }

    /** @type {Map<string, string>} switching channel alias → the key of its controlling channel */
    this.switching = new Map();
    for (const [key, definition] of Object.entries(this.channels)) {
      for (const capability of capabilitiesOf(definition)) {
        const aliases = Object.keys(capability.switchChannels ?? {});
        for (const alias of aliases) {
          this.switching.set(alias, key);
        }
      }
    }
  }

  /**
   * @param {string} key - A channel key, possibly with a pixel key in it.
   * @param {Map<string, object>} names - Template channel keys (with `$pixelKey`) → value.
   * @returns {object | undefined} The value of the first template the key matches.
   */
  patternMatch(key, names) {
    for (const [template, value] of names) {
      const pattern = escapeRegExp(template).replaceAll(escapeRegExp(PIXEL_KEY), '(.+)');
      if (new RegExp(`^(?:${pattern})$`).test(key)) {
        return value;
      }
    }
    return undefined;
  }

  /**
   * @param {string} key - A channel key of a mode.
   * @returns {Ref} The channel.
   */
  lookup(key) {
    if (Object.hasOwn(this.channels, key)) {
      return { name: key, definition: this.channels[key] };
    }
    if (Object.hasOwn(this.templates, key)) {
      return { name: key, definition: this.templates[key] };
    }
    if (this.fineOf.has(key)) {
      return { name: key, definition: this.fineOf.get(key), fine: true };
    }
    // before the plain templates: "Dimmer Master fine" also fits "Dimmer $pixelKey"
    const fine = this.patternMatch(key, this.fineOf);
    if (fine !== undefined) {
      return { name: key, definition: fine, fine: true };
    }
    const template = this.patternMatch(key, new Map(Object.entries(this.templates)));
    if (template !== undefined) {
      return { name: key, definition: template };
    }
    throw new ConversionError(`unknown channel '${key}'`);
  }

  /**
   * @param {string} alias - A switching channel's key.
   * @param {string[]} modeKeys - The channel keys of the mode.
   * @returns {Ref} The switching channel with the controlling channel at its default value.
   */
  resolveSwitching(alias, modeKeys) {
    const controller = this.switching.get(alias);
    if (!modeKeys.includes(controller)) {
      throw new ConversionError(`switching channel '${alias}': its controlling channel '${controller}' is not in the mode`);
    }
    const definition = this.channels[controller];
    const value = defaultValue(definition);
    const range = ranges8(definition).find(({ start, end }) => start <= value && value <= end);
    if (range === undefined) {
      throw new ConversionError(`switching channel '${alias}': default ${value} of '${controller}' is in no capability`);
    }
    const target = range.capability.switchChannels?.[alias];
    if (target === undefined || target === null) {
      const option_ = alias.split(' / ').map((option) => option.trim()).find((option) => !option.startsWith('NoFunction'));
      return { name: `${option_ ?? alias} (unused)`, definition: { capability: { type: 'NoFunction' } }, unused: true };
    }
    return this.lookup(target);
  }

  /**
   * @param {string | string[]} repeatFor - A matrix insert's `repeatFor`.
   * @returns {string[]} The pixel (or pixel group) keys it repeats for.
   */
  pixelKeys(repeatFor) {
    if (Array.isArray(repeatFor)) {
      return repeatFor;
    }
    if (repeatFor === 'eachPixelGroup') {
      return Object.keys(this.matrix.pixelGroups ?? {});
    }
    if (repeatFor.startsWith('eachPixel')) {
      if ('pixelKeys' in this.matrix) {
        return this.matrix.pixelKeys.flat(PIXEL_KEYS_DEPTH).filter((key) => key !== null);
      }
      const count = (this.matrix.pixelCount ?? [1, 1, 1]).reduce((product, size) => product * size, 1);
      return Array.from({ length: count }, (_, index) => String(index + 1));
    }
    throw new ConversionError(`unknown repeatFor '${repeatFor}'`);
  }
}

// --------------------------------------------------------------------------- classification

/**
 * @param {Ref} ref - A channel.
 * @returns {Item} What the channel is for PitchControl.
 */
function classify(ref) {
  if (ref.fine || ref.unused) {
    return { kind: 'const', ref };
  }
  const capabilities = capabilitiesOf(ref.definition);
  const types = new Set(capabilities.map((capability) => capability.type));
  if (types.size === 1 && types.has('ColorIntensity') && capabilities.length === 1) {
    return { kind: 'colour', ref, colour: capabilities[0].color };
  }
  if (types.size === 1 && types.has('Intensity') && capabilities.length === 1) {
    return { kind: 'dimmer', ref };
  }
  const strobes = capabilities.some((capability) => capability.type === 'ShutterStrobe' && capability.shutterEffect === 'Strobe');
  // (a function channel: sound control, then strobe)
  return { kind: strobes && [...types].every((type) => ['ShutterStrobe', 'NoFunction', 'Effect'].includes(type)) ? 'shutter' : 'const', ref };
}

/**
 * @param {object} capability - A strobe capability.
 * @returns {number} How fast it gets at its end (a frequency in Hz; 1000 for "fast"; -1 when OFL gives no number).
 */
function strobeSpeed(capability) {
  const end = 'speedEnd' in capability ? capability.speedEnd : capability.speed;
  if (typeof end === 'string') {
    const match = /^([\d.]+)\s*Hz$/.exec(end);
    if (match) {
      return Number(match[1]);
    }
    if (end === 'fast') {
      return 1000;
    }
  }
  return -1;
}

/**
 * @param {Ref} ref - A shutter channel.
 * @returns {{open: number, strobo: number}} The open value and the fastest plain strobe value.
 */
function deriveShutter(ref) {
  const ranges = ranges8(ref.definition);
  const isOpener = ({ capability }) => (capability.type === 'ShutterStrobe' && capability.shutterEffect === 'Open') || capability.type === 'NoFunction';
  const openers = ranges.filter((range) => isOpener(range)).toSorted((a, b) => a.start - b.start || a.end - b.end);
  let open = 0;
  if (openers.length > 0) {
    const { start, end } = openers[0];
    open = start === 0 ? 0 : Math.floor((start + end + 1) / 2); // "LED off" 0..31, "on" 32..63: the middle of "on"
  }
  const strobes = ranges.filter(({ capability }) => capability.type === 'ShutterStrobe' && capability.shutterEffect === 'Strobe');
  const plain = strobes.filter(({ capability }) => !capability.randomTiming && !('durationStart' in capability) && !('duration' in capability));
  const pool = plain.length > 0 ? plain : strobes;
  if (pool.length === 0) {
    throw new ConversionError(`shutter channel '${ref.name}' has no strobe range`);
  }
  let best = pool[0];
  for (const range of pool) {
    if (strobeSpeed(range.capability) >= strobeSpeed(best.capability)) { // the last of equally fast ranges wins
      best = range;
    }
  }
  return { open, strobo: best.end };
}

/**
 * @param {Ref} ref - A channel.
 * @returns {number | undefined} The middle of a colour-preset channel's "White" step.
 */
function whitePreset(ref) {
  for (const { start, end, capability } of ranges8(ref.definition)) {
    if (capability.type === 'ColorPreset' && (capability.comment ?? '').trim().toLowerCase() === 'white') {
      return Math.floor((start + end + 1) / 2);
    }
  }
  return undefined;
}

// --------------------------------------------------------------------------- modes

/**
 * @param {FixtureData} fixtureData - The fixture.
 * @param {object} mode - An OFL mode.
 * @returns {(Item | Block)[]} The mode's channels in order, with switching channels resolved and matrix inserts as blocks.
 */
function flatten(fixtureData, mode) {
  const keys = mode.channels.filter((channel) => typeof channel === 'string');
  return mode.channels.map((entry) => {
    if (entry === null) {
      throw new ConversionError('a channel that OFL leaves out (null)');
    }
    if (typeof entry === 'object') {
      if (entry.insert !== 'matrixChannels') {
        throw new ConversionError(`unknown insert '${entry.insert}'`);
      }
      const pixels = fixtureData.pixelKeys(entry.repeatFor);
      if ((entry.channelOrder ?? 'perPixel') !== 'perPixel' && pixels.length > 1) {
        throw new ConversionError('channels ordered per channel, not per pixel');
      }
      return { keys: pixels, items: entry.templateChannels.map((key) => classify(fixtureData.lookup(key))) };
    }
    const isSwitching = fixtureData.switching.has(entry) && !Object.hasOwn(fixtureData.channels, entry);
    return classify(isSwitching ? fixtureData.resolveSwitching(entry, keys) : fixtureData.lookup(entry));
  });
}

/**
 * @param {string[]} colours - The colours of a run of colour channels.
 * @returns {string | undefined} `RGB` or `RGBW` when they form one.
 */
function formatOf(colours) {
  return FORMATS.get(colours.map((colour) => (WHITES.has(colour) ? 'White' : colour)).join('|'));
}

/**
 * @param {Item | Block} entry - An entry of a flattened mode.
 * @returns {boolean} Whether it is a block.
 */
function isBlock(entry) {
  return 'keys' in entry;
}

/**
 * @param {Item | Block} entry - An entry of a flattened mode.
 * @returns {boolean} Whether it is a colour channel outside a block.
 */
function isColourItem(entry) {
  return !isBlock(entry) && entry.kind === 'colour';
}

/**
 * @param {Block} block - A block of shutter channels, repeated for pixel groups.
 * @returns {Item[]} One shutter channel for each group, named by the group.
 */
function expandShutterBlock(block) {
  return block.keys.flatMap((key) => block.items.map((item) => ({
    kind: 'shutter',
    ref: { name: item.ref.name.replaceAll(PIXEL_KEY, () => key), definition: item.ref.definition },
  })));
}

/**
 * A strobe per pixel group becomes one shutter channel each (named by the group); a block of colours is the pixel
 * block; anything else per pixel can't be expressed.
 * @param {(Item | Block)[]} items - A flattened mode.
 * @returns {{expanded: (Item | Block)[], colourBlock: Block | undefined}} The mode with the shutter blocks expanded.
 */
function expandBlocks(items) {
  const expanded = [];
  let colourBlock;
  for (const entry of items) {
    if (!isBlock(entry)) {
      expanded.push(entry);
      continue;
    }
    const kinds = new Set(entry.items.map((item) => item.kind));
    if (kinds.size === 1 && kinds.has('shutter')) {
      expanded.push(...expandShutterBlock(entry));
    }
    else if (kinds.size === 1 && kinds.has('colour')) {
      if (colourBlock !== undefined) {
        throw new ConversionError('more than one pixel block');
      }
      colourBlock = entry;
      expanded.push(entry);
    }
    else {
      throw new ConversionError(`a per-pixel block with ${entry.items.map((item) => item.ref.name).join(', ')}`);
    }
  }
  return { expanded, colourBlock };
}

/**
 * Colour channels in a flat list: R G B (W) next to each other are the pixel block of a one-pixel mode.
 * @param {(Item | Block)[]} expanded - The mode, changed in place: the run becomes a block.
 * @returns {{format: string, block: Block} | undefined} The block, or nothing when the mode has no colour channels.
 */
function findColourRun(expanded) {
  const runStart = expanded.findIndex((entry) => isColourItem(entry));
  if (runStart === -1) {
    return undefined;
  }
  for (const length of [4, 3]) {
    const run = expanded.slice(runStart, runStart + length);
    const format = run.length === length && run.every((entry) => isColourItem(entry)) ? formatOf(run.map((entry) => entry.colour)) : undefined;
    if (format) {
      const block = { keys: ['1'], items: run };
      expanded.splice(runStart, length, block);
      return { format, block };
    }
  }
  throw new ConversionError('colour channels that don\'t start with R G B');
}

/**
 * @param {Item} item - The channel.
 * @param {boolean} hasColourBlock - Whether the mode has a pixel block.
 * @param {object[]} slots - The slots built so far.
 * @returns {object} The slot for the channel.
 */
function slotOf(item, hasColourBlock, slots) {
  const { ref } = item;
  if (item.kind === 'colour') { // amber, UV, ... or a second white: no pixel colour, held off
    return { name: ref.name, value: defaultValue(ref.definition) };
  }
  if (item.kind === 'dimmer') {
    if (hasColourBlock) {
      return { name: ref.name, value: 255 }; // held at full: the colours carry the brightness
    }
    if (slots.some((existing) => existing.pixels === 'I')) {
      throw new ConversionError('more than one dimmer without colour channels');
    }
    return { name: ref.name, pixels: 'I' }; // follows the brightness
  }
  if (item.kind === 'shutter') {
    return { name: ref.name, shutter: deriveShutter(ref) };
  }
  let value = defaultValue(ref.definition);
  if (!hasColourBlock && !ref.fine && !ref.unused) {
    value = whitePreset(ref) || value;
  }
  return { name: ref.name, value };
}

/**
 * @param {FixtureData} fixtureData - The fixture.
 * @param {object} mode - An OFL mode.
 * @returns {{pixels: number, channels: object[]}} The mode as PitchControl has it.
 */
function convertMode(fixtureData, mode) {
  const { expanded, colourBlock: matrixBlock } = expandBlocks(flatten(fixtureData, mode));
  let colourBlock = matrixBlock;
  let format;
  let pixels = 1;
  if (colourBlock === undefined) {
    const run = findColourRun(expanded);
    if (run) {
      colourBlock = run.block;
      format = run.format;
    }
  }
  else {
    if (expanded.some((entry) => isColourItem(entry))) {
      throw new ConversionError('colour channels both inside and outside a pixel block');
    }
    format = formatOf(colourBlock.items.map((item) => item.colour));
    if (format === undefined) {
      throw new ConversionError(`pixel colours ${colourBlock.items.map((item) => item.colour).join(' ')} are not RGB or RGBW`);
    }
    pixels = colourBlock.keys.length;
  }

  const hasColourBlock = colourBlock !== undefined;
  const slots = [];
  for (const entry of expanded) {
    slots.push(isBlock(entry) ? { pixels: format } : slotOf(entry, hasColourBlock, slots));
  }
  return { pixels, channels: slots };
}

/**
 * @param {object} mode - An OFL mode.
 * @returns {string} The name of the PitchControl mode: "4ch 1" → "4CH1", "D3ch" → "D3CH" (the names the fixtures' displays and manuals use), else OFL's name.
 */
function modeName(mode) {
  const short = mode.shortName || mode.name;
  const match = /^(d?)(\d+)ch[ -]?(\d*)$/i.exec(short);
  return match ? `${match[1].toUpperCase()}${match[2]}CH${match[3]}` : mode.name;
}

/**
 * @param {string} name - A mode's name.
 * @returns {string} The mode's id: lower case, anything but letters and digits is a hyphen.
 */
export function modeId(name) {
  const slug = [...name.toLowerCase()].map((character) => (/[\p{L}\p{N}]/u.test(character) ? character : '-')).join('');
  return slug.split('-').filter(Boolean).join('-') || 'mode';
}

/**
 * @param {{name: string, pixels: number, channels: object[]}} mode - A converted mode.
 * @returns {string} One line of the mode's layout, naming every constant and its value.
 */
function describe(mode) {
  const parts = mode.channels.map((slot) => {
    if ('pixels' in slot && slot.pixels !== 'I') {
      return mode.pixels > 1 ? `${mode.pixels} × ${slot.pixels}` : slot.pixels;
    }
    if ('pixels' in slot) {
      return `${slot.name} (follows the brightness)`;
    }
    if ('shutter' in slot || slot.name.endsWith('(unused)')) { // a channel that does nothing in the colour-mixing function
      return slot.name;
    }
    if (slot.value === 255) {
      return `${slot.name} (held at full)`;
    }
    return slot.value ? `${slot.name} (held at ${slot.value})` : `${slot.name} (off)`;
  });
  let text = parts.join(', ');
  text = `${text.slice(0, 1).toUpperCase()}${text.slice(1)}.`;
  const kinds = new Set(mode.channels.map((slot) => slot.pixels));
  if (!kinds.has('RGB') && !kinds.has('RGBW')) {
    text += kinds.has('I')
      ? ' No colour mixing in this mode: only the brightness follows PitchControl.'
      : ' PitchControl can\'t change the light in this mode (no colour or dimmer channel); it is listed for addressing.';
  }
  return text;
}

/**
 * @param {object} data - The OFL fixture JSON.
 * @returns {Converted} Every OFL mode as a PitchControl channel mode (`ofl_mode` names the OFL mode it came from); modes it can't express go to `skipped`, with the reason.
 */
export function convertFixture(data) {
  const fixtureData = new FixtureData(data);
  const result = { modes: [], skipped: [] };
  for (const mode of data.modes) {
    let converted;
    try {
      converted = convertMode(fixtureData, mode);
    }
    catch (error) {
      if (error instanceof ConversionError) {
        result.skipped.push([mode.name, error.message]);
        continue;
      }
      throw error;
    }
    const name = modeName(mode);
    const pitchControlMode = { id: modeId(name), name, description: '', ofl_mode: mode.name, ...converted };
    pitchControlMode.description = describe(pitchControlMode);
    result.modes.push(pitchControlMode);
  }
  return result;
}

/**
 * @param {string} why - The reason a mode was skipped, as `convertFixture` words it.
 * @returns {string} The reason in words for a person (the same words as the import report in the app).
 */
export function shortReason(why) {
  if (why.startsWith('a per-pixel block')) {
    return 'a dimmer, amber, CCT or strobe per pixel, which PitchControl can\'t repeat';
  }
  if (why.includes('leaves out (null)')) {
    return 'an empty gap channel between the pixels';
  }
  return why.startsWith('pixel colours') ? 'amber next to RGB on every pixel' : why;
}
