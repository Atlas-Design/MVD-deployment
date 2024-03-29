FROM local

COPY --from=root sd_models /workdir/ComfyUI/models
COPY --from=root sd_scripts /workdir/sd_scripts

COPY --from=comfywr-root ComfyUI /workdir/ComfyUI
COPY --from=comfywr-root custom_nodes /workdir/custom_nodes
COPY --from=comfywr-root comfywr /workdir/comfywr
