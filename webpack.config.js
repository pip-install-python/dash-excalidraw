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
            // Respect ESM "exports" conditions in @excalidraw/excalidraw 0.18+.
            //
            // Setting conditionNames REPLACES webpack's defaults, which is why
            // the mode condition has to be re-added by hand. 0.18's exports map
            // declares `./index.css` under ONLY "development" and "production"
            // — there is no "default" branch to fall through to — so without
            // the mode condition here the stylesheet import fails to resolve:
            //   Module not found: "./index.css" is not exported under the
            //   conditions ["import","module","require","default"]
            //
            // Order matters only within the package's own exports map, so
            // listing exactly one mode condition keeps dev builds on
            // dist/dev/* and production builds on dist/prod/*.
            conditionNames: [
                mode === 'development' ? 'development' : 'production',
                'import',
                'module',
                'require',
                'default',
            ],
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
                    // 0.18 ships its UI font (Assistant) as real .woff2 files
                    // referenced from its stylesheet. Emitting them as separate
                    // assets would require a working publicPath, which Dash's
                    // cache-busted component-suite URLs do not give us, so the
                    // font requests would 404 and the UI would fall back to a
                    // system font. Inlining costs ~106 KB of base64 and keeps
                    // the component a single self-contained file.
                    test: /\.woff2?$/,
                    type: 'asset/inline',
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
        optimization: {
            // Excalidraw 0.18 lazy-loads large subsystems (mermaid, the image
            // cropper, the command palette) behind dynamic import(). Left
            // alone, webpack emits ~136 async chunks beside the main file.
            // Dash registers and serves ONLY the files named in
            // `_js_dist`, and webpack's runtime resolves chunk URLs relative
            // to its own script origin — which under Dash is a cache-busted
            // `/_dash-component-suites/...v0_1_0m<hash>.js` path that no chunk
            // matches. Every lazy feature would 404 on first use.
            splitChunks: false,
        },
        plugins: [
            // The other half of the single-file guarantee: splitChunks:false
            // stops *vendor* splitting, but each dynamic import() still gets
            // its own chunk. Merging to one chunk inlines them all.
            new webpack.optimize.LimitChunkCountPlugin({maxChunks: 1}),
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