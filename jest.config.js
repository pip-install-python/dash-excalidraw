/**
 * The JavaScript harness. Scope is deliberate and narrow: the two behaviours
 * Python tests cannot see — the command dispatcher's readiness/id handling,
 * and the export correlation.
 *
 * `build:backends` has always passed `--ignore \.test\.` to
 * dash-generate-components, so test files beside the component are skipped by
 * the Python stub generator. That slot was designed for this and sat empty
 * until now.
 */
module.exports = {
    testEnvironment: 'jsdom',
    roots: ['<rootDir>/src/ts'],
    testMatch: ['**/*.test.ts', '**/*.test.tsx'],
    moduleNameMapper: {
        // Excalidraw's real entry is reachable only through its package
        // `exports` map, which jest's CommonJS resolver does not read — the
        // same constraint tsconfig.json documents for moduleResolution. Map
        // the specifier instead of fighting resolution.
        '^@excalidraw/excalidraw$': '<rootDir>/src/ts/__mocks__/excalidraw.tsx',
        '\\.css$': '<rootDir>/src/ts/__mocks__/styleMock.js',
    },
    transform: {
        '^.+\\.tsx?$': [
            'ts-jest',
            {
                // Jest runs CommonJS; the build's tsconfig targets ESNext for
                // webpack. Override only what the runner needs.
                tsconfig: {
                    jsx: 'react',
                    module: 'commonjs',
                    moduleResolution: 'node',
                    target: 'ES2020',
                    esModuleInterop: true,
                    allowSyntheticDefaultImports: true,
                    strict: false,
                    skipLibCheck: true,
                },
                // Type-checking is webpack's job (ts-loader) and CI runs the
                // build. Enforcing it twice would make an unrelated typing
                // change fail the behavioural suite.
                diagnostics: false,
            },
        ],
    },
    clearMocks: true,
};
