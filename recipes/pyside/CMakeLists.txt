cmake_minimum_required(VERSION 3.22)
cmake_policy(VERSION 3.22)

project(pyside6_recipe)

if(NOT PYSIDE_SOURCE_DIR)
    message(FATAL_ERROR "PYSIDE_SOURCE_DIR must point at the extracted Qt for Python source")
endif()

# Preserve the upstream super-project behavior while omitting both Shiboken subprojects.
set(is_pyside6_superproject_build 1)
add_subdirectory("${PYSIDE_SOURCE_DIR}/sources/pyside6" sources/pyside6)
add_subdirectory("${PYSIDE_SOURCE_DIR}/sources/pyside-tools" sources/pyside-tools)

