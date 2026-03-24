cmake_minimum_required(VERSION 3.20)
project(kddockwidgets)

find_package(Git REQUIRED)
find_package(Qt6 REQUIRED COMPONENTS Core Gui Widgets PrintSupport)
find_package(Python3 REQUIRED COMPONENTS Interpreter Development.Module)

#[[
    Helper to find the filesystem path of a Python module.
    Uses the current Python interpreter to query the module's __path__.
]]
function(resolve_python_package_path module_name out_var)
    execute_process(
        COMMAND "${Python3_EXECUTABLE}" -c "import ${module_name}; print(${module_name}.__path__[0])"
        RESULT_VARIABLE result
        OUTPUT_VARIABLE output
        ERROR_VARIABLE error
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    if(NOT result EQUAL 0)
        message(FATAL_ERROR "Failed to resolve Python package '${module_name}': ${error}")
    endif()
    set(${out_var} "${output}" PARENT_SCOPE)
endfunction()


# Patching Helpers

#[[
    Applies a git patch if it hasn't been applied yet.
    First checks if the patch applies cleanly, then attempts to apply it.
    If it fails, it checks if the patch was already applied by trying a reverse check.
]]
function(apply_git_patch_if_needed patch_file working_directory)
    get_filename_component(patch_name "${patch_file}" NAME)

    # Check if patch can be applied cleanly
    execute_process(
        COMMAND "${GIT_EXECUTABLE}" apply --check "${patch_file}"
        WORKING_DIRECTORY "${working_directory}"
        RESULT_VARIABLE patch_check_result
        ERROR_VARIABLE patch_check_error
        OUTPUT_QUIET
    )

    if(patch_check_result EQUAL 0)
        execute_process(
            COMMAND "${GIT_EXECUTABLE}" apply "${patch_file}"
            WORKING_DIRECTORY "${working_directory}"
            RESULT_VARIABLE patch_result
        )
        if(NOT patch_result EQUAL 0)
            message(FATAL_ERROR "Failed to apply patch: ${patch_name}")
        endif()
        message(STATUS "Applied patch: ${patch_name}")
        return()
    endif()

    # If it can't be applied, check if it was already applied (by trying to reverse it)
    execute_process(
        COMMAND "${GIT_EXECUTABLE}" apply --check --reverse "${patch_file}"
        WORKING_DIRECTORY "${working_directory}"
        RESULT_VARIABLE patch_reverse_result
        OUTPUT_QUIET
        ERROR_QUIET
    )
    if(patch_reverse_result EQUAL 0)
        message(STATUS "Patch already applied: ${patch_name}")
    else()
        message(FATAL_ERROR
            "Patch cannot be applied or reversed: ${patch_name}\n"
            "${patch_check_error}")
    endif()
endfunction()

#[[
    Asserts that a file contains a specific snippet of code.
    Used to verify that submodule patches were applied correctly.
]]
function(assert_file_contains path expected_snippet)
    file(READ "${path}" contents)
    string(FIND "${contents}" "${expected_snippet}" snippet_index)
    if(snippet_index EQUAL -1)
        message(FATAL_ERROR
            "Expected vendored KDDockWidgets change is missing from ${path}:\n"
            "${expected_snippet}")
    endif()
endfunction()

#[[
    Validates that vendor-specific changes are present in the submodule.
    Checks for critical lines in the KDDockWidgets source tree.
]]
function(validate_vendored_kddockwidgets source_dir)
    assert_file_contains(
        "${source_dir}/python/PyKDDockWidgets/CMakeLists.txt"
        "set(PyKDDockWidgets_target_include_directories \${PROJECT_SOURCE_DIR}/src)"
    )
    assert_file_contains(
        "${source_dir}/python/PyKDDockWidgets/CMakeLists.txt"
        "\${PROJECT_SOURCE_DIR}/src/qtwidgets/views/MainWindow.h"
    )
    assert_file_contains(
        "${source_dir}/python/PyKDDockWidgets/typesystem_kddockwidgets.xml"
        "<!-- <enum-type name=\"ViewType\" /> workaround: shiboken 6.10.2 generates duplicate symbols -->"
    )
endfunction()

# Python Binding Paths Configuration
message(STATUS "Configuring Python binding components...")

resolve_python_package_path("shiboken6" shiboken_dir)
resolve_python_package_path("shiboken6_generator" shiboken_gen_dir)
resolve_python_package_path("PySide6" pyside_dir)

# Platform-specific library and binary suffixes
if(WIN32)
    set(shiboken_library "${shiboken_dir}/shiboken6.abi3.lib")
    set(shiboken_binary "${shiboken_gen_dir}/shiboken6.exe")
    set(pyside_library "${pyside_dir}/pyside6.abi3.lib")
elseif(APPLE)
    set(shiboken_library "${shiboken_dir}/libshiboken6.abi3.dylib")
    set(shiboken_binary "${shiboken_gen_dir}/shiboken6")
    set(pyside_library "${pyside_dir}/libpyside6.abi3.dylib")
else()
    set(shiboken_library "${shiboken_dir}/libshiboken6.abi3.so")
    set(shiboken_binary "${shiboken_gen_dir}/shiboken6")
    set(pyside_library "${pyside_dir}/libpyside6.abi3.so")
endif()

# Export paths as cache variables for the KDDockWidgets build system
# This handles the discovery to ensure consistency across submodules and custom scripts
set(SHIBOKEN_DIR "${shiboken_dir}" CACHE PATH "Path to shiboken6 package")
set(SHIBOKEN_GEN_DIR "${shiboken_gen_dir}" CACHE PATH "Path to shiboken6_generator package")
set(PYSIDE_DIR "${pyside_dir}" CACHE PATH "Path to PySide6 package")

set(SHIBOKEN_LIBRARY "${shiboken_library}" CACHE PATH "Path to shiboken6 library")
set(SHIBOKEN_BINARY "${shiboken_binary}" CACHE PATH "Path to shiboken6 generator binary")
set(SHIBOKEN_INCLUDE_DIR "${shiboken_dir}/include" CACHE PATH "Path to shiboken6 headers")

set(PYSIDE_LIBRARY "${pyside_library}" CACHE PATH "Path to PySide6 library")
set(PYSIDE_INCLUDE_DIR "${pyside_dir}/include" CACHE PATH "Path to PySide6 headers")
set(PYSIDE_TYPESYSTEMS "${pyside_dir}/typesystems" CACHE PATH "Path to PySide6 typesystem files")

# Submodule Preparation & Patching ---
set(KDDockWidgets_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/submodules/KDDockWidgets")

if(NOT EXISTS "${KDDockWidgets_SOURCE_DIR}/CMakeLists.txt")
    message(FATAL_ERROR
        "KDDockWidgets source not found at ${KDDockWidgets_SOURCE_DIR}.\n"
        "Did you forget to clone submodules?")
endif()

# Apply all patches from the patches directory
file(GLOB PATCH_FILES "${CMAKE_CURRENT_SOURCE_DIR}/patches/*.patch")
foreach(PATCH_FILE ${PATCH_FILES})
    apply_git_patch_if_needed("${PATCH_FILE}" "${KDDockWidgets_SOURCE_DIR}")
endforeach()

# Build Configuration
set(PYTHON_BINDING_NAMESPACE "PyKDDockWidgetsQt6" CACHE STRING "Python wrapper namespace")

# Verify the submodule is in the expected state before building
validate_vendored_kddockwidgets("${KDDockWidgets_SOURCE_DIR}")

# Build KDDockWidgets as a sub-project
add_subdirectory("${KDDockWidgets_SOURCE_DIR}" "KDDockWidgets_build")

# Stub Generation & Installation
find_program(
    SHIBOKEN6_GENPYI_PATH
    NAMES shiboken6-genpyi shiboken6-genpyi.exe
)

# Prepare __init__.pyi from template
configure_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/${PYTHON_BINDING_NAMESPACE}/__init__.pyi.in"
    "${CMAKE_CURRENT_BINARY_DIR}/__init__.pyi"
    @ONLY
)

set(PYTHON_PACKAGE_INSTALL_FILES
    "${CMAKE_CURRENT_BINARY_DIR}/__init__.pyi"
    "${CMAKE_CURRENT_SOURCE_DIR}/${PYTHON_BINDING_NAMESPACE}/py.typed"
)

# Setup stub generation if generator is available
if(SHIBOKEN6_GENPYI_PATH)
    message(STATUS "Found shiboken6-genpyi: ${SHIBOKEN6_GENPYI_PATH}")
    add_custom_target(
        generate_kddockwidgets_stubs ALL
        COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/scripts/gen_stubs.py"
                "${SHIBOKEN6_GENPYI_PATH}"
                "$<TARGET_FILE_DIR:PyKDDockWidgets>"
                "$<TARGET_FILE:PyKDDockWidgets>"
                "${PYTHON_BINDING_NAMESPACE}"
                "$<TARGET_FILE_DIR:PyKDDockWidgets>"
                "$<TARGET_FILE_DIR:KDAB::kddockwidgets>"
                "$<TARGET_FILE_DIR:Qt6::Core>"
                "${SHIBOKEN_DIR}"
                "${PYSIDE_DIR}"
        DEPENDS PyKDDockWidgets
        COMMENT "Generating stubs for KDDockWidgets..."
    )
    list(APPEND PYTHON_PACKAGE_INSTALL_FILES
        "$<TARGET_FILE_DIR:PyKDDockWidgets>/KDDockWidgets.pyi"
    )
else()
    message(WARNING "shiboken6-genpyi not found on PATH; skipping stub generation.")
endif()

install(FILES ${PYTHON_PACKAGE_INSTALL_FILES} DESTINATION "${PYTHON_BINDING_NAMESPACE}")
