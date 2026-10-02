import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['src/generated']),
  {
    files: ['**/*.ts'],
    extends: [js.configs.recommended, tseslint.configs.recommended],
    languageOptions: { ecmaVersion: 2022 },
    rules: {
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },
  // The renderer is one pure function: a Blueprint in, files out. It imports
  // nothing but its own modules, so it cannot reach the console, the network
  // or the filesystem, and it reads no clock and no randomness, so the same
  // Blueprint is always the same files.
  {
    files: ['src/**/*.ts'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              regex: '^[^.]',
              message:
                'The renderer imports only its own modules: no console, no network, no filesystem.',
            },
          ],
        },
      ],
      'no-restricted-globals': [
        'error',
        { name: 'Date', message: 'The renderer reads no clock.' },
        { name: 'performance', message: 'The renderer reads no clock.' },
        { name: 'fetch', message: 'The renderer reaches no network.' },
        { name: 'process', message: 'The renderer reads no environment.' },
        { name: 'crypto', message: 'The renderer uses no randomness.' },
      ],
      'no-restricted-properties': [
        'error',
        {
          object: 'Math',
          property: 'random',
          message: 'The renderer uses no randomness.',
        },
      ],
    },
  },
])
