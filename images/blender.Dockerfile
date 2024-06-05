FROM local

COPY --from=root tools /workdir/tools
COPY --from=root sd_scripts /workdir/sd_scripts
COPY --from=root configs /workdir/configs
COPY --from=root blender_scripts /workdir/blender_scripts
COPY --from=root blendwr /workdir/blendwr

COPY --from=root sd_models/segment_anything /workdir/sd_models/segment_anything