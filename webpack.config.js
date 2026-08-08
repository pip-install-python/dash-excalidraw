const path = require('path');
const webpack = require('webpack');

const packagejson = require('./package.json');

const dashLibraryName = packagejson.name.replace(/-/g, '_');

module.exports = function (env, argv) {
    const mode = (argv && argv.mode) || 'production';
    const entry = [path.join(__dirname, 'src/ts/index.ts')];
    const output = {
        path: path.join(__dirname, dashLibraryName),
        filename: `${dashLibraryName}.js`,
        library: dashLibraryName,
        libraryTarget: 'umd',
        globalObject: 'this',
    };

    // React and ReactDOM are provided by Dash at runtime — do not bundle them.
    // Excalidraw is bundled into our output because there is no host-provided copy.
    const externals = {
        react: {
            commonjs: 'react',
            commonjs2: 'react',
            amd: 'react',
            umd: 'react',
            root: 'React',
        },
        'react-dom': {
            commonjs: 'react-dom',
            commonjs2: 'react-dom',
            amd: 'react-dom',
            umd: 'react-dom',
            root: 'ReactDOM',
        },
    };

    return {
        output,
        mode,
        entry,
        target: 'web',
        externals,
        resolve: {
            extensions: ['.ts', '.tsx', '.js', '.jsx', '.json'],
            // Respect ESM "exports" conditions in @excalidraw/excalidraw 0.18+
            conditionNames: ['import', 'module', 'require', 'default'],
        },
        experiments: {
            // Dash loads the bundle via a classic <script>, not <script type=module>.
            outputModule: false,
        },
        module: {
            rules: [
                {
                    // Excalidraw's ESM imports omit .js extensions; webpack 5 strict ESM
                    // mode would reject them without this.
                    test: /\.m?js$/,
                    resolve: {fullySpecified: false},
                },
                {
                    test: /\.tsx?$/,
                    use: 'ts-loader',
                    exclude: /node_modules/,
                },
                {
                    test: /\.css$/,
                    use: [
                        {
                            loader: 'style-loader',
                            options: {
                                insert: function insertAtTop(element) {
                                    var parent = document.querySelector('head');
                                    var lastInsertedElement =
                                        window._lastElementInsertedByStyleLoader;

                                    if (!lastInsertedElement) {
                                        parent.insertBefore(element, parent.firstChild);
                                    } else if (lastInsertedElement.nextSibling) {
                                        parent.insertBefore(element, lastInsertedElement.nextSibling);
                                    } else {
                                        parent.appendChild(element);
                                    }

                                    window._lastElementInsertedByStyleLoader = element;
                                },
                            },
                        },
                        {
                            loader: 'css-loader',
                        },
                    ],
                },
            ],
        },
        performance: {
            hints: false,
        },
        plugins: [
            // Excalidraw's bundled UMD/ESM references process.env.NODE_ENV and
            // process.env.IS_PREACT at runtime. The browser has no `process`
            // global, so we substitute the values at build time. Without this
            // the Excalidraw module throws `ReferenceError: process is not
            // defined` as soon as it is require()'d.
            new webpack.DefinePlugin({
                'process.env.NODE_ENV': JSON.stringify(mode),
                'process.env.IS_PREACT': JSON.stringify('false'),
            }),
        ],
    };
};