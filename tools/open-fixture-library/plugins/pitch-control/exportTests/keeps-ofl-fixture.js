import { isDeepStrictEqual } from 'util';
import { oflJsonOf } from '../type-file.js';
/** @import { Fixture } from '../../../lib/model/Fixture.js' */

/** The major version of OFL's fixture schema the conversion was written for (the same number as `OFL_SCHEMA_MAJOR` in PitchControl's `ofl/importer.py`). */
const SUPPORTED_SCHEMA_MAJOR = 12;

/**
 * @typedef {object} ExportFile
 * @property {string} name File name, may include slashes to provide a folder structure.
 * @property {string} content File content.
 * @property {string} mimetype File mime type.
 * @property {Fixture[] | null} fixtures Fixture objects that are described in given file; may be omitted if the file doesn't belong to any fixture (e.g. manufacturer information).
 * @property {string | null} mode Mode's shortName if given file only describes a single mode.
 */

/**
 * The OFL fixture a type file was made from, built back from what the file keeps: the top-level keys in
 * `source.key_order`, with `$schema` and `name` from `source` and `modes` from `ofl_modes`
 * (`rebuild_ofl` in PitchControl's `ofl/importer.py`).
 * @param {object} type - The parsed type file.
 * @returns {object} The OFL fixture.
 */
function rebuildOflFixture(type) {
  const values = { $schema: type.source.schema, name: type.source.name, modes: type.ofl_modes };
  return Object.fromEntries(
    type.source.key_order
      .map((key) => [key, key in values ? values[key] : type[key]])
      .filter(([, value]) => value !== undefined && value !== null),
  );
}

/**
 * Checks that the file keeps the OFL fixture it was made from, whole, that every mode says which OFL mode it is,
 * and that OFL's schema is still the one the conversion was written for.
 * @param {ExportFile} exportFile - The file returned by the plugins' export module.
 * @param {ExportFile[]} allExportFiles - An array of all export files.
 * @returns {Promise<void, string[] | string>} Resolve when the test passes or reject with an array of errors or one error if the test fails.
 */
export default async function testKeepsOflFixture(exportFile, allExportFiles) {
  const type = JSON.parse(exportFile.content);
  const errors = [];

  const { source } = type;
  if (source?.format !== 'ofl' || typeof source.fixture !== 'string' || !Array.isArray(source.key_order)) {
    throw new Error('source needs format "ofl", the fixture\'s key and key_order');
  }

  const schemaMajor = Number(String(source.schema_version).split('.', 1)[0]);
  if (schemaMajor !== SUPPORTED_SCHEMA_MAJOR) {
    errors.push(`OFL's fixture schema is ${source.schema_version}, the conversion was written for ${SUPPORTED_SCHEMA_MAJOR}.x: update convert.js and type-file.js with PitchControl's ofl/convert.py (see the README of the plugin)`);
  }

  const oflModeNames = new Set((type.ofl_modes ?? []).map((mode) => mode.name));
  for (const mode of type.modes) {
    if (!oflModeNames.has(mode.ofl_mode)) {
      errors.push(`mode ${mode.name}: ofl_mode '${mode.ofl_mode}' is not one of the kept OFL modes`);
    }
  }

  const [fixture] = exportFile.fixtures ?? [];
  if (fixture && !isDeepStrictEqual(rebuildOflFixture(type), oflJsonOf(fixture.jsonObject))) {
    errors.push('the kept OFL data does not rebuild the OFL fixture');
  }

  if (errors.length > 0) {
    throw errors;
  }
}
