cmake_minimum_required(VERSION 3.19)
project(ispc-texture-compressor CXX ISPC)

if(NOT DEFINED ISPC_TEXCOMP_SRC_DIR)
    set(ISPC_TEXCOMP_SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
endif()

set(SRC_DIR "${ISPC_TEXCOMP_SRC_DIR}/ispc_texcomp")

add_library(ispc_texcomp
    "${SRC_DIR}/ispc_texcomp.cpp"
    "${SRC_DIR}/ispc_texcomp_astc.cpp"
    "${SRC_DIR}/kernel.ispc"
    "${SRC_DIR}/kernel_astc.ispc"
)

if(CMAKE_SYSTEM_PROCESSOR MATCHES "AMD64|x86_64|x64")
    set_target_properties(ispc_texcomp PROPERTIES
        ISPC_INSTRUCTION_SETS "sse2-i32x4;avx1-i32x8"
    )
elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64|ARM64")
    set_target_properties(ispc_texcomp PROPERTIES
        ISPC_INSTRUCTION_SETS "neon-i32x4"
    )
endif()

target_compile_options(ispc_texcomp PRIVATE
    $<$<COMPILE_LANGUAGE:ISPC>:--opt=fast-math>
)

target_include_directories(ispc_texcomp PUBLIC
    $<BUILD_INTERFACE:${SRC_DIR}>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}>
    $<INSTALL_INTERFACE:include>
)

if(WIN32 AND BUILD_SHARED_LIBS)
    set_target_properties(ispc_texcomp PROPERTIES
        WINDOWS_EXPORT_ALL_SYMBOLS ON
    )
endif()

include(GNUInstallDirs)
install(TARGETS ispc_texcomp
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)
install(FILES "${SRC_DIR}/ispc_texcomp.h"
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
)

# The bundled DirectXTex command-line tools (texconv/texassemble/texdiag) are host-side asset-pipeline utilities.
# Their DirectXMath HDR colour matrices use nested brace-initialization of XMMATRIX, which does not compile for ARM64 (NEON) DirectXMath,
# and an ARM64 build of these tools could not run on an x64 build host anyway.
# Restrict them (and the DirectXTex lib they need) to x64.
if(WIN32 AND CMAKE_SYSTEM_PROCESSOR MATCHES "AMD64|x86_64|x64")
    set(DXTEX_ROOT "${ISPC_TEXCOMP_SRC_DIR}/ISPC Texture Compressor/DirectXTex")
    set(DXTEX_SRC "${DXTEX_ROOT}/DirectXTex")

    add_library(DirectXTex STATIC
        "${DXTEX_SRC}/BC.cpp"
        "${DXTEX_SRC}/BC4BC5.cpp"
        "${DXTEX_SRC}/BC6HBC7.cpp"
        "${DXTEX_SRC}/BCDirectCompute.cpp"
        "${DXTEX_SRC}/DirectXTexCompress.cpp"
        "${DXTEX_SRC}/DirectXTexCompressGPU.cpp"
        "${DXTEX_SRC}/DirectXTexConvert.cpp"
        "${DXTEX_SRC}/DirectXTexD3D11.cpp"
        "${DXTEX_SRC}/DirectXTexDDS.cpp"
        "${DXTEX_SRC}/DirectXTexFlipRotate.cpp"
        "${DXTEX_SRC}/DirectXTexHDR.cpp"
        "${DXTEX_SRC}/DirectXTexImage.cpp"
        "${DXTEX_SRC}/DirectXTexMipMaps.cpp"
        "${DXTEX_SRC}/DirectXTexMisc.cpp"
        "${DXTEX_SRC}/DirectXTexNormalMaps.cpp"
        "${DXTEX_SRC}/DirectXTexPMAlpha.cpp"
        "${DXTEX_SRC}/DirectXTexResize.cpp"
        "${DXTEX_SRC}/DirectXTexTGA.cpp"
        "${DXTEX_SRC}/DirectXTexUtil.cpp"
        "${DXTEX_SRC}/DirectXTexWIC.cpp"
    )
    target_include_directories(DirectXTex PUBLIC "${DXTEX_SRC}")
    target_compile_definitions(DirectXTex PRIVATE
        _UNICODE UNICODE
        _WIN32_WINNT=0x0600
        _WIN7_PLATFORM_UPDATE
        _CRT_STDIO_ARBITRARY_WIDE_SPECIFIERS
    )
    target_link_libraries(DirectXTex PRIVATE d3d11.lib dxgi.lib d3dcompiler.lib uuid.lib)

    foreach(tool IN ITEMS texassemble texconv texdiag)
        if(tool STREQUAL "texassemble")
            set(_src "${DXTEX_ROOT}/Texassemble/texassemble.cpp")
        elseif(tool STREQUAL "texconv")
            set(_src "${DXTEX_ROOT}/Texconv/Texconv.cpp")
        elseif(tool STREQUAL "texdiag")
            set(_src "${DXTEX_ROOT}/Texdiag/texdiag.cpp")
        endif()
        add_executable(${tool} "${_src}")
        target_compile_definitions(${tool} PRIVATE
            _UNICODE UNICODE
            _WIN32_WINNT=0x0600
            _CONSOLE
        )
        target_link_libraries(${tool} PRIVATE DirectXTex ole32.lib windowscodecs.lib uuid.lib)
    endforeach()

    install(TARGETS texassemble texconv texdiag
        RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
    )
endif()
