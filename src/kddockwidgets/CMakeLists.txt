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

# Resolve package directories via Python to handle transient overlay paths (e.g. from pip/uv)
resolve_python_package_path("shiboken6" shiboken_dir)
resolve_python_package_path("shiboken6_generator" shiboken_gen_dir)
resolve_python_package_path("PySide6" pyside_dir)

message(STATUS "Resolved shiboken_dir: ${shiboken_dir}")
message(STATUS "Resolved shiboken_gen_dir: ${shiboken_gen_dir}")
message(STATUS "Resolved pyside_dir: ${pyside_dir}")

# Helper to find a file using recursive globbing
function(find_file_robust label dir pattern out_var)
    file(GLOB_RECURSE candidates "${dir}/${pattern}")
    if(candidates)
        # Prefer the shortest path (likely the most direct one)
        list(SORT candidates)
        list(GET candidates 0 found_file)
        set(${out_var} "${found_file}" PARENT_SCOPE)
        message(STATUS "Found ${label}: ${found_file}")
    else()
        set(${out_var} "${out_var}-NOTFOUND" PARENT_SCOPE)
        message(STATUS "Could NOT find ${label} in ${dir} with pattern ${pattern}")
    endif()
endfunction()

# Find libraries - use patterns that handle lib prefix and extensions
if(WIN32)
    find_file_robust("SHIBOKEN_LIBRARY" "${shiboken_dir}" "shiboken6*.lib" SHIBOKEN_LIBRARY_FILE)
    find_file_robust("SHIBOKEN_BINARY" "${shiboken_gen_dir}" "shiboken6.exe" SHIBOKEN_BINARY_FILE)
    find_file_robust("PYSIDE_LIBRARY" "${pyside_dir}" "pyside6*.lib" PYSIDE_LIBRARY_FILE)
else()
    find_file_robust("SHIBOKEN_LIBRARY" "${shiboken_dir}" "libshiboken6*.abi3*" SHIBOKEN_LIBRARY_FILE)
    find_file_robust("SHIBOKEN_BINARY" "${shiboken_gen_dir}" "shiboken6" SHIBOKEN_BINARY_FILE)
    find_file_robust("PYSIDE_LIBRARY" "${pyside_dir}" "libpyside6*.abi3*" PYSIDE_LIBRARY_FILE)
endif()

# Debugging backup: if still missing, show full tree
if(NOT SHIBOKEN_LIBRARY_FILE OR NOT SHIBOKEN_BINARY_FILE OR NOT PYSIDE_LIBRARY_FILE)
    file(GLOB_RECURSE ALL_FILES "${shiboken_dir}/*")
    message(STATUS "Full directory contents of ${shiboken_dir}: ${ALL_FILES}")
    message(FATAL_ERROR "Python binding discovery failed. See logs above for file listing.")
endif()

# Export paths as cache variables for the KDDockWidgets build system
set(SHIBOKEN_DIR "${shiboken_dir}" CACHE PATH "Path to shiboken6 package")
set(SHIBOKEN_GEN_DIR "${shiboken_gen_dir}" CACHE PATH "Path to shiboken6_generator package")
set(PYSIDE_DIR "${pyside_dir}" CACHE PATH "Path to PySide6 package")

set(SHIBOKEN_LIBRARY "${SHIBOKEN_LIBRARY_FILE}" CACHE PATH "Path to shiboken6 library")
set(SHIBOKEN_BINARY "${SHIBOKEN_BINARY_FILE}" CACHE PATH "Path to shiboken6 generator binary")
set(SHIBOKEN_INCLUDE_DIR "${shiboken_dir}/include" CACHE PATH "Path to shiboken6 headers")

set(PYSIDE_LIBRARY "${PYSIDE_LIBRARY_FILE}" CACHE PATH "Path to PySide6 library")
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

# Post-subdirectory target fixes for Windows wheels
# Sometimes the imported targets from PySide6Config.cmake are missing the location properties
# on Windows when using unofficial/wheel installs.
if(WIN32)
    if(TARGET PySide6::pyside6)
        get_target_property(implib PySide6::pyside6 IMPORTED_IMPLIB)
        if(NOT implib OR implib MATCHES "NOTFOUND")
            set_target_properties(PySide6::pyside6 PROPERTIES IMPORTED_IMPLIB "${PYSIDE_LIBRARY}")
        endif()
    endif()
    if(TARGET Shiboken6::libshiboken)
        get_target_property(implib Shiboken6::libshiboken IMPORTED_IMPLIB)
        if(NOT implib OR implib MATCHES "NOTFOUND")
            set_target_properties(Shiboken6::libshiboken PROPERTIES IMPORTED_IMPLIB "${SHIBOKEN_LIBRARY}")
        endif()
    endif()
    if(TARGET Shiboken6::shiboken)
        get_target_property(loc Shiboken6::shiboken IMPORTED_LOCATION)
        if(NOT loc OR loc MATCHES "NOTFOUND")
            set_target_properties(Shiboken6::shiboken PROPERTIES IMPORTED_LOCATION "${SHIBOKEN_BINARY}")
        endif()
    endif()
endif()

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
