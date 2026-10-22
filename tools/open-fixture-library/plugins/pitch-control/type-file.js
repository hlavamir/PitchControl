/**
 * @fileoverview
 * One OFL fixture → the file PitchControl keeps for a fixture type, with the OFL data it came from.
 *
 * This is the port of `backend/src/pitchcontrol/ofl/importer.py` (`import_fixture`) plus the way the app writes the
 * result (`FixtureType.model_dump` in `config/models.py`: its key order, and its fix-ups of the mode ids). The shape
 * is described in the docstring of `importer.py` and in README.md next to this file.
 */

/* eslint-disable camelcase -- the keys of PitchControl's file format are snake_case */
import { convertFixture } from './convert.js';

/** The version of the mapping. The same number as `CONVERTER_VERSION` in PitchControl's `ofl/importer.py`. */
export const CONVERTER_VERSION = 1;

const OFL_SITE = 'https://open-fixture-library.org';
const LICENSE = 'MIT';

/** OFL's top-level keys that are not kept under their own name. */
const NOT_KEPT = new Set(['$schema', 'name', 'modes']);

/** The OFL keys PitchControl's fixture type declares, in the order the app writes them (any other key follows). */
const DECLARED_OFL_KEYS = new Set([
  'shortName',
  'categories',
  'meta',
  'comment',
  'links',
  'helpWanted',
  'rdm',
  'physical',
  'matrix',
  'wheels',
  'availableChannels',
  'templateChannels',
]);

/** What PitchControl's own fields of a fixture type are before anything is imported. */
const DEFAULT_GAMMA = 1;
const DEFAULT_STROBO_COLOR = { h: 0, s: 0, b: 1 };

/**
 * A type name is a file name (letters, digits, space, - _ . and at most 64): the manufacturer first unless the
 * fixture name has it already, "/" becomes "-" ("LED Bar 240/8" → "Stairville LED Bar 240-8").
 * @param {string | undefined} manufacturer - The manufacturer's name.
 * @param {string} fixtureName - The fixture's name.
 * @returns {string} The type name.
 */
export function typeName(manufacturer, fixtureName) {
  let text = fixtureName.trim();
  if (manufacturer && !text.toLowerCase().startsWith(manufacturer.toLowerCase())) {
    const maker = manufacturer.trim();
    const isLowerCase = maker === maker.toLowerCase() && maker !== maker.toUpperCase();
    text = `${isLowerCase ? maker.slice(0, 1).toUpperCase() + maker.slice(1) : maker} ${text}`; // OFL has "cameo"
  }
  text = text.replaceAll('/', '-').normalize('NFKD');
  text = text.replaceAll(/[^\w .-]/g, '').replaceAll(/\s+/g, ' ').trim().replace(/^[ _.-]+/, '');
  return text.slice(0, 64).trimEnd() || 'Imported fixture';
}

/**
 * The OFL JSON as the repository has it: OFL's model embeds the gobo resources of a wheel slot into the fixture
 * (`resource: "gobos/biohazard"` becomes the resource's whole data), which the repository's JSON doesn't have.
 * @param {object} jsonObject - The fixture's JSON from OFL's model.
 * @returns {object} A copy with the resource names back.
 */
export function oflJsonOf(jsonObject) {
  const data = structuredClone(jsonObject);
  const wheels = Object.values(data.wheels ?? {});
  for (const wheel of wheels) {
    for (const slot of wheel.slots) {
      if (typeof slot.resource === 'object' && slot.resource !== null) {
        slot.resource = slot.resource.alias ? `${slot.resource.type}/aliases/${slot.resource.alias}` : `${slot.resource.type}/${slot.resource.key}`;
      }
    }
  }
  return data;
}

/**
 * What the app does when it loads a type (`_complete_modes` in `config/models.py`): a mode id used twice gets `-2`,
 * `-3` … on the later one.
 * @param {object[]} modes - The converted modes.
 */
function makeModeIdsUnique(modes) {
  const seen = new Set();
  for (const mode of modes) {
    const wanted = mode.id;
    let number = 2;
    while (seen.has(mode.id)) {
      mode.id = `${wanted}-${number}`;
      number += 1;
    }
    seen.add(mode.id);
  }
}

/**
 * @param {object} data - The OFL fixture JSON.
 * @param {string} key - OFL's key of the fixture, "manufacturer-key/fixture-key".
 * @param {string | undefined} manufacturer - The manufacturer's name.
 * @param {string} schemaVersion - The version of OFL's fixture schema.
 * @returns {object} The type's `source` block (see `importer.py`).
 */
function sourceOf(data, key, manufacturer, schemaVersion) {
  const source = {
    format: 'ofl',
    fixture: key,
    name: data.name,
    manufacturer,
    url: `${OFL_SITE}/${key}`,
    schema: data.$schema,
    license: LICENSE,
    converter: CONVERTER_VERSION,
    key_order: Object.keys(data),
    schema_version: schemaVersion,
  };
  return Object.fromEntries(Object.entries(source).filter(([, value]) => value !== undefined && value !== null));
}

/**
 * @param {object} data - The OFL fixture JSON.
 * @param {string} key - OFL's key of the fixture, "manufacturer-key/fixture-key".
 * @param {string | undefined} manufacturer - The manufacturer's name.
 * @param {object[]} modes - The converted modes.
 * @returns {string} The type's description.
 */
function describeType(data, key, manufacturer, modes) {
  const shown = manufacturer && !data.name.toLowerCase().startsWith(manufacturer.toLowerCase()) ? `${manufacturer} ${data.name}` : data.name;
  const categories = Array.isArray(data.categories) && data.categories.length > 0 ? ` (${data.categories.join(', ')})` : '';
  return `${shown}${categories}. Imported from the Open Fixture Library (MIT licence, ${key}). `
    + `Modes: ${modes.map((mode) => mode.name).join(', ')}; ${modes[0].name} is the default. Check the type against the manual.`;
}

/**
 * @typedef {object} TypeFile
 * @property {string} name The type's name, which is its file name (without `.json`).
 * @property {object | undefined} content The file's content; nothing when no mode of the fixture can be expressed.
 * @property {[string, string][]} skipped The OFL modes left out, with the reason.
 */

/**
 * The type file the app would save after File → Import Fixture → Open Fixture Library of this fixture, as far as the
 * plugin can know it: without where the copy was fetched from (`source.commit`, `source.file`) and without the
 * app's own `app_version` stamp.
 * @param {object} data - The fixture's JSON as the repository has it (`oflJsonOf`).
 * @param {object} origin - What OFL's model knows besides the JSON.
 * @param {string} origin.key - OFL's key of the fixture, "manufacturer-key/fixture-key".
 * @param {string | undefined} origin.manufacturer - The manufacturer's name.
 * @param {string} origin.schemaVersion - The version of OFL's fixture schema.
 * @returns {TypeFile} The type file.
 */
export function buildTypeFile(data, { key, manufacturer, schemaVersion }) {
  const converted = convertFixture(data);
  const name = typeName(manufacturer, data.name);
  if (converted.modes.length === 0) {
    return { name, content: undefined, skipped: converted.skipped };
  }

  const defaultMode = converted.modes[0].id;
  makeModeIdsUnique(converted.modes);

  const content = {
    description: describeType(data, key, manufacturer, converted.modes),
    transport: 'dmx',
    modes: converted.modes.map((mode) => ({
      id: mode.id,
      name: mode.name,
      description: mode.description,
      pixels: mode.pixels,
      channels: mode.channels,
      ofl_mode: mode.ofl_mode,
    })),
    default_mode: defaultMode,
    gamma: DEFAULT_GAMMA,
    strobo_color: DEFAULT_STROBO_COLOR,
    source: sourceOf(data, key, manufacturer, schemaVersion),
    ofl_modes: data.modes,
  };
  for (const declared of DECLARED_OFL_KEYS) {
    if (declared in data) {
      content[declared] = data[declared];
    }
  }
  for (const [otherKey, value] of Object.entries(data)) {
    if (!NOT_KEPT.has(otherKey) && !DECLARED_OFL_KEYS.has(otherKey)) {
      content[otherKey] = value;
    }
  }
  return { name, content, skipped: converted.skipped };
}
