/* Adapter: mount a Svelte 4 component as a dockview-core panel.

   dockview-core is framework-agnostic — a panel is an IContentRenderer
   ({ element, init(params), dispose() }). This wraps a Svelte component so each
   panel instantiates it into its own element and tears it down on dispose. */

export function svelteRenderer(Component) {
  return () => {
    const element = document.createElement('div');
    element.className = 'dock-panel';
    let instance;
    return {
      element,
      init(parameters) {
        instance = new Component({
          target: element,
          props: { ...(parameters.params || {}), panelApi: parameters.api },
        });
      },
      dispose() {
        instance?.$destroy?.();
      },
    };
  };
}

/* Build the createComponent map dockview calls per panel name. */
export function componentFactory(map) {
  const renderers = Object.fromEntries(
    Object.entries(map).map(([name, Component]) => [name, svelteRenderer(Component)]),
  );
  return ({ name }) => {
    const make = renderers[name];
    if (!make) throw new Error(`unknown dockview panel: ${name}`);
    return make();
  };
}
