/// <reference types="vite/client" />

declare module "plotly.js-basic-dist-min" {
  const Plotly: {
    toImage: (
      graphDiv: HTMLElement,
      options: { format: "png"; width?: number; height?: number; scale?: number }
    ) => Promise<string>;
  };
  export default Plotly;
}
