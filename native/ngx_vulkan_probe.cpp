// SPDX-License-Identifier: MIT
// Copyright (c) 2026 thekozugroup
// Headless capability diagnostic; this never enables a production video engine.
// Link NVIDIA's separately provisioned SDK wrapper, not guessed driver symbols.
#include <vulkan/vulkan.h>
#include "nvsdk_ngx_vk.h"
#include "nvsdk_ngx_defs_dlssg.h"
#include <algorithm>
#include <clocale>
#include <cstdio>
#include <cwchar>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef POPCORN_VULKAN_SMOKE
#include "dlssg_smoke.hpp"
#endif

namespace {
constexpr const char* project_id = "fb597f3f-5797-44d5-a4e6-59b757758233";
void log_sink(const char*, NVSDK_NGX_Logging_Level, NVSDK_NGX_Feature) {}

std::wstring wide(const char* text) {
    std::mbstate_t state{};
    const char* input = text;
    auto size = std::mbsrtowcs(nullptr, &input, 0, &state);
    if (size == static_cast<std::size_t>(-1)) throw std::runtime_error("Invalid UTF-8 path");
    std::wstring result(size + 1, L'\0');
    input = text; state = {};
    std::mbsrtowcs(result.data(), &input, result.size(), &state);
    return result;
}

void vk_check(VkResult result, const char* operation) {
    if (result != VK_SUCCESS) {
        std::fprintf(stderr, "%s: Vulkan result %d\n", operation, result);
        throw std::runtime_error("Vulkan operation failed");
    }
}

void ngx_result(const char* key, NVSDK_NGX_Result value) {
    std::printf(",\"%s\":\"0x%08x\"", key, static_cast<unsigned int>(value));
    std::fflush(stdout);
}

bool extensions(const std::vector<VkExtensionProperties>& available, uint32_t count,
                VkExtensionProperties* required, std::vector<const char*>& names) {
    bool supported = true;
    std::printf(",\"extensions\":[");
    for (uint32_t i = 0; i < count; ++i) {
        const char* name = required[i].extensionName;
        bool found = std::any_of(available.begin(), available.end(), [name](const auto& value) {
            return std::string(value.extensionName) == name;
        });
        std::printf("%s{\"name\":\"%s\",\"available\":%s}", i ? "," : "", name, found ? "true" : "false");
        if (found) names.push_back(name);
        else supported = false;
    }
    std::printf("]");
    return supported;
}

struct Session {
    VkInstance instance = VK_NULL_HANDLE;
    VkDevice device = VK_NULL_HANDLE;
    VkCommandPool pool = VK_NULL_HANDLE;
    NVSDK_NGX_Parameter* parameters = nullptr;
    NVSDK_NGX_Handle* feature = nullptr;
    bool initialized = false;
    ~Session() {
        if (device) vkDeviceWaitIdle(device);
        if (feature) NVSDK_NGX_VULKAN_ReleaseFeature(feature);
        if (parameters) NVSDK_NGX_VULKAN_DestroyParameters(parameters);
        if (initialized) NVSDK_NGX_VULKAN_Shutdown1(device);
        if (pool) vkDestroyCommandPool(device, pool, nullptr);
        if (device) vkDestroyDevice(device, nullptr);
        if (instance) vkDestroyInstance(instance, nullptr);
    }
};
}

int main(int argc, char** argv) {
    std::setlocale(LC_ALL, "");
    if ((argc != 4 && argc != 5) || (std::string(argv[3]) != "sr" && std::string(argv[3]) != "fg") || (argc == 5 && (std::string(argv[3]) != "fg" || (std::string(argv[4]) != "--create" && std::string(argv[4]) != "--render")))) {
        std::fprintf(stderr, "Usage: ngx-vulkan-probe SDK-library-folder scratch-folder sr|fg [--create|--render (fg only)]\n");
        return 2;
    }
    std::printf("{\"api\":\"Vulkan\",\"feature\":\"%s\",\"video_render_verified\":false", argv[3]);
    bool capability_completed = false;
    bool fg_created = false;
    bool pixels_verified = false;
    try {
        Session session;
        auto sdk_path = wide(argv[1]), scratch = wide(argv[2]);
        const wchar_t* library_path = sdk_path.c_str();
        NVSDK_NGX_FeatureCommonInfo common{};
        common.PathListInfo = {&library_path, 1};
        common.LoggingInfo = {log_sink, NVSDK_NGX_LOGGING_LEVEL_OFF, true};
        NVSDK_NGX_FeatureDiscoveryInfo discovery{};
        discovery.SDKVersion = NVSDK_NGX_Version_API;
        discovery.FeatureID = std::string(argv[3]) == "fg" ? NVSDK_NGX_Feature_FrameGeneration : NVSDK_NGX_Feature_SuperSampling;
        discovery.Identifier.IdentifierType = NVSDK_NGX_Application_Identifier_Type_Project_Id;
        discovery.Identifier.v.ProjectDesc = {project_id, NVSDK_NGX_ENGINE_TYPE_CUSTOM, "PopcornSR"};
        discovery.ApplicationDataPath = scratch.c_str();
        discovery.FeatureInfo = &common;

        uint32_t needed_count = 0;
        VkExtensionProperties* needed = nullptr;
        auto result = NVSDK_NGX_VULKAN_GetFeatureInstanceExtensionRequirements(&discovery, &needed_count, &needed);
        ngx_result("instance_extension_result", result);
        if (result != NVSDK_NGX_Result_Success) throw std::runtime_error("NGX instance discovery failed");
        uint32_t count = 0;
        vk_check(vkEnumerateInstanceExtensionProperties(nullptr, &count, nullptr), "Instance extension count");
        std::vector<VkExtensionProperties> available(count);
        vk_check(vkEnumerateInstanceExtensionProperties(nullptr, &count, available.data()), "Instance extensions");
        std::vector<const char*> instance_names;
        std::printf(",\"instance_requirements\":{");
        std::printf("\"count\":%u", needed_count);
        bool present = extensions(available, needed_count, needed, instance_names);
        std::printf("}");
        if (!present) throw std::runtime_error("Required instance extension unavailable");

        VkApplicationInfo app{};
        app.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
        app.pApplicationName = "Popcorn SR capability check";
        app.apiVersion = VK_API_VERSION_1_3;
        VkInstanceCreateInfo creation{};
        creation.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
        creation.pApplicationInfo = &app;
        creation.enabledExtensionCount = instance_names.size();
        creation.ppEnabledExtensionNames = instance_names.data();
        vk_check(vkCreateInstance(&creation, nullptr, &session.instance), "Create instance");
        vk_check(vkEnumeratePhysicalDevices(session.instance, &count, nullptr), "Physical device count");
        std::vector<VkPhysicalDevice> devices(count);
        vk_check(vkEnumeratePhysicalDevices(session.instance, &count, devices.data()), "Physical devices");
        VkPhysicalDevice physical = VK_NULL_HANDLE;
        VkPhysicalDeviceProperties properties{};
        for (auto device : devices) {
            vkGetPhysicalDeviceProperties(device, &properties);
            if (properties.vendorID == 0x10de) { physical = device; break; }
        }
        if (!physical) throw std::runtime_error("No NVIDIA Vulkan physical device");
        // Device names from Vulkan contain no control characters on supported drivers.
        std::printf(",\"device\":\"%s\",\"api_version\":%u", properties.deviceName, properties.apiVersion);
        if (properties.apiVersion < VK_API_VERSION_1_3) throw std::runtime_error("Probe requires Vulkan 1.3");
        NVSDK_NGX_FeatureRequirement requirement{};
        result = NVSDK_NGX_VULKAN_GetFeatureRequirements(session.instance, physical, &discovery, &requirement);
        ngx_result("feature_requirement_result", result);
        if (result == NVSDK_NGX_Result_Success) {
            std::printf(",\"feature_support_flags\":%u,\"minimum_architecture\":%u", static_cast<unsigned int>(requirement.FeatureSupported), requirement.MinHWArchitecture);
        } else {
            // Zero-initialized output is not a successful support verdict.
            std::printf(",\"feature_support_flags\":null,\"minimum_architecture\":null");
        }

        needed_count = 0; needed = nullptr;
        auto device_result = NVSDK_NGX_VULKAN_GetFeatureDeviceExtensionRequirements(session.instance, physical, &discovery, &needed_count, &needed);
        ngx_result("device_extension_result", device_result);
        if (device_result != NVSDK_NGX_Result_Success) throw std::runtime_error("NGX device discovery failed");
        vk_check(vkEnumerateDeviceExtensionProperties(physical, nullptr, &count, nullptr), "Device extension count");
        available.resize(count);
        vk_check(vkEnumerateDeviceExtensionProperties(physical, nullptr, &count, available.data()), "Device extensions");
        std::vector<const char*> device_names;
        std::printf(",\"device_requirements\":{\"count\":%u", needed_count);
        present = extensions(available, needed_count, needed, device_names);
        std::printf("}");
        if (!present) throw std::runtime_error("Required device extension unavailable");

        vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, nullptr);
        std::vector<VkQueueFamilyProperties> families(count);
        vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, families.data());
        uint32_t family = count;
        for (uint32_t i = 0; i < count; ++i) {
            if ((families[i].queueFlags & (VK_QUEUE_GRAPHICS_BIT | VK_QUEUE_COMPUTE_BIT)) == (VK_QUEUE_GRAPHICS_BIT | VK_QUEUE_COMPUTE_BIT)) { family = i; break; }
        }
        if (family == count) throw std::runtime_error("No graphics/compute queue");
        VkPhysicalDeviceVulkan11Features f11{}; f11.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_1_FEATURES;
        VkPhysicalDeviceVulkan12Features f12{}; f12.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES;
        VkPhysicalDeviceVulkan13Features f13{}; f13.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES;
        f11.pNext = &f12; f12.pNext = &f13;
        VkPhysicalDeviceOpticalFlowFeaturesNV optical{}; optical.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_OPTICAL_FLOW_FEATURES_NV;
        if (std::find_if(device_names.begin(), device_names.end(), [](const char* name) { return std::string(name) == VK_NV_OPTICAL_FLOW_EXTENSION_NAME; }) != device_names.end()) f13.pNext = &optical;
        VkPhysicalDeviceFeatures2 features{}; features.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2; features.pNext = &f11;
        vkGetPhysicalDeviceFeatures2(physical, &features);
        float priority = 1.0f;
        VkDeviceQueueCreateInfo queue{}; queue.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
        queue.queueFamilyIndex = family; queue.queueCount = 1; queue.pQueuePriorities = &priority;
        VkDeviceCreateInfo device_info{}; device_info.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
        device_info.pNext = &features; device_info.queueCreateInfoCount = 1; device_info.pQueueCreateInfos = &queue;
        device_info.enabledExtensionCount = device_names.size(); device_info.ppEnabledExtensionNames = device_names.data();
        vk_check(vkCreateDevice(physical, &device_info, nullptr, &session.device), "Create device");

        result = NVSDK_NGX_VULKAN_Init_with_ProjectID(project_id, NVSDK_NGX_ENGINE_TYPE_CUSTOM, "PopcornSR", scratch.c_str(), session.instance, physical, session.device, vkGetInstanceProcAddr, vkGetDeviceProcAddr, &common);
        ngx_result("init_result", result);
        if (result != NVSDK_NGX_Result_Success) throw std::runtime_error("NGX Vulkan initialization failed");
        session.initialized = true;
        result = NVSDK_NGX_VULKAN_GetCapabilityParameters(&session.parameters);
        ngx_result("capability_result", result);
        if (result != NVSDK_NGX_Result_Success || !session.parameters) throw std::runtime_error("NGX capability query failed");
        const char* names[] = {"SuperSampling.Available", "SuperSampling.FeatureInitResult", "VideoSuperResolution.Available", "VideoSuperResolution.FeatureInitResult", "FrameGeneration.Available", "FrameGeneration.FeatureInitResult", "FrameGeneration.NeedsUpdatedDriver", "FrameGeneration.MinDriverVersionMajor", "FrameGeneration.MinDriverVersionMinor", "FrameInterpolation.Available", "FrameInterpolation.FeatureInitResult"};
        std::printf(",\"parameters\":{");
        for (std::size_t i = 0; i < sizeof(names) / sizeof(names[0]); ++i) {
            int value = 0;
            auto query = session.parameters->Get(names[i], &value);
            std::printf("%s\"%s\":{\"query_result\":\"0x%08x\",\"value\":%d}", i ? "," : "", names[i], static_cast<unsigned int>(query), value);
        }
        std::printf("}");
        capability_completed = true;
        if (argc == 5) {
            int available_fg = 0;
            if (session.parameters->Get(NVSDK_NGX_Parameter_FrameGeneration_Available, &available_fg) != NVSDK_NGX_Result_Success || !available_fg) throw std::runtime_error("Frame Generation unavailable; creation skipped");
            VkCommandPoolCreateInfo pool_info{}; pool_info.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
            pool_info.queueFamilyIndex = family;
            vk_check(vkCreateCommandPool(session.device, &pool_info, nullptr, &session.pool), "Create command pool");
            VkCommandBufferAllocateInfo allocation{}; allocation.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
            allocation.commandPool = session.pool; allocation.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY; allocation.commandBufferCount = 1;
            VkCommandBuffer command = VK_NULL_HANDLE;
            vk_check(vkAllocateCommandBuffers(session.device, &allocation, &command), "Allocate command buffer");
            VkCommandBufferBeginInfo begin{}; begin.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
            begin.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
            vk_check(vkBeginCommandBuffer(command, &begin), "Begin command buffer");
            session.parameters->Set(NVSDK_NGX_Parameter_CreationNodeMask, 1u);
            session.parameters->Set(NVSDK_NGX_Parameter_VisibilityNodeMask, 1u);
            session.parameters->Set(NVSDK_NGX_Parameter_Width, 256u);
            session.parameters->Set(NVSDK_NGX_Parameter_Height, 192u);
            session.parameters->Set(NVSDK_NGX_DLSSG_Parameter_BackbufferFormat, static_cast<unsigned int>(VK_FORMAT_R8G8B8A8_UNORM));
            result = NVSDK_NGX_VULKAN_CreateFeature(command, NVSDK_NGX_Feature_FrameGeneration, session.parameters, &session.feature);
            ngx_result("fg_create_result", result);
            if (result != NVSDK_NGX_Result_Success || !session.feature) throw std::runtime_error("Frame Generation creation failed");
            vk_check(vkEndCommandBuffer(command), "End command buffer");
            VkQueue gpu_queue = VK_NULL_HANDLE;
            vkGetDeviceQueue(session.device, family, 0, &gpu_queue);
            VkSubmitInfo submit{}; submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
            submit.commandBufferCount = 1; submit.pCommandBuffers = &command;
            vk_check(vkQueueSubmit(gpu_queue, 1, &submit, VK_NULL_HANDLE), "Submit creation");
            vk_check(vkQueueWaitIdle(gpu_queue), "Wait for creation");
            fg_created = true;
            if (std::string(argv[4]) == "--render") {
#ifdef POPCORN_VULKAN_SMOKE
                pixels_verified = popcorn_dlssg::smoke(physical, session.device, family, session.feature, session.parameters);
                if (!pixels_verified) throw std::runtime_error("Generated-frame pixel check failed");
#else
                throw std::runtime_error("Rebuild with POPCORN_VULKAN_SMOKE for pixel evaluation");
#endif
            }
        }
        std::printf(",\"capability_check_completed\":true,\"fg_creation_verified\":%s,\"pixel_render_verified\":%s}\n", fg_created ? "true" : "false", pixels_verified ? "true" : "false");
        return 0;
    } catch (const std::exception& error) {
        std::printf(",\"error\":\"%s\",\"capability_check_completed\":%s,\"fg_creation_verified\":%s,\"pixel_render_verified\":false}\n", error.what(), capability_completed ? "true" : "false", fg_created ? "true" : "false");
        return 1;
    }
}
