class HarfbuzzOptions:
    shared: bool
    fPIC: bool
    with_glib: bool
    with_gdi: bool
    with_uniscribe: bool
    with_directwrite: bool
    with_subset: bool
    with_coretext: bool


class Recipe:
    options: HarfbuzzOptions