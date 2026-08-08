/**
 * Every Dash component receives these props automatically.
 *
 * Usage:
 * ```ts
 * type Props = {
 *   my_prop: string;
 * } & DashComponentProps;
 * ```
 */
export type DashComponentProps = {
    /**
     * Unique ID to identify this component in Dash callbacks.
     */
    id?: string;
    /**
     * Dash-assigned callback that writes props back to the store.
     */
    setProps: (props: Record<string, any>) => void;
};