// SPDX-License-Identifier: MIT
// Copyright (c) 2026 thekozugroup
// Small synchronous Vulkan transfer resources for native video processing.
#pragma once
#include <vulkan/vulkan.h>
#include <cstdint>
#include <cstring>
#include <stdexcept>

namespace popcorn_vk {
inline void check(VkResult result, const char* operation) {
    if (result != VK_SUCCESS) throw std::runtime_error(operation);
}

inline uint32_t memory_type(VkPhysicalDevice physical, uint32_t allowed, VkMemoryPropertyFlags flags) {
    VkPhysicalDeviceMemoryProperties memory{};
    vkGetPhysicalDeviceMemoryProperties(physical, &memory);
    for (uint32_t index = 0; index < memory.memoryTypeCount; ++index) {
        if ((allowed & (1u << index)) && (memory.memoryTypes[index].propertyFlags & flags) == flags) return index;
    }
    throw std::runtime_error("Required Vulkan memory type unavailable");
}

struct Buffer {
    VkDevice device;
    VkBuffer handle = VK_NULL_HANDLE;
    VkDeviceMemory memory = VK_NULL_HANDLE;
    void* mapped = nullptr;
    VkDeviceSize size;
    Buffer(VkPhysicalDevice physical, VkDevice gpu, VkDeviceSize bytes) : device(gpu), size(bytes) {
        try {
            VkBufferCreateInfo info{}; info.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
            info.size = size;
            info.usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT | VK_BUFFER_USAGE_STORAGE_BUFFER_BIT | VK_BUFFER_USAGE_SHADER_DEVICE_ADDRESS_BIT;
            info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
            check(vkCreateBuffer(device, &info, nullptr, &handle), "Vulkan buffer creation failed");
            VkMemoryRequirements required{}; vkGetBufferMemoryRequirements(device, handle, &required);
            VkMemoryAllocateFlagsInfo address{}; address.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_FLAGS_INFO;
            address.flags = VK_MEMORY_ALLOCATE_DEVICE_ADDRESS_BIT;
            VkMemoryAllocateInfo allocation{}; allocation.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
            allocation.pNext = &address; allocation.allocationSize = required.size;
            allocation.memoryTypeIndex = memory_type(physical, required.memoryTypeBits, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
            check(vkAllocateMemory(device, &allocation, nullptr, &memory), "Vulkan buffer allocation failed");
            check(vkBindBufferMemory(device, handle, memory, 0), "Vulkan buffer binding failed");
            check(vkMapMemory(device, memory, 0, size, 0, &mapped), "Vulkan buffer mapping failed");
        } catch (...) { close(); throw; }
    }
    Buffer(const Buffer&) = delete;
    Buffer& operator=(const Buffer&) = delete;
    void close() {
        if (mapped) vkUnmapMemory(device, memory);
        if (handle) vkDestroyBuffer(device, handle, nullptr);
        if (memory) vkFreeMemory(device, memory, nullptr);
        mapped = nullptr; handle = VK_NULL_HANDLE; memory = VK_NULL_HANDLE;
    }
    ~Buffer() { close(); }
};

struct Image {
    VkDevice device;
    VkImage handle = VK_NULL_HANDLE;
    VkImageView view = VK_NULL_HANDLE;
    VkDeviceMemory memory = VK_NULL_HANDLE;
    VkFormat format;
    uint32_t width, height;
    VkImageLayout layout = VK_IMAGE_LAYOUT_UNDEFINED;
    Image(VkPhysicalDevice physical, VkDevice gpu, uint32_t w, uint32_t h, VkFormat pixel_format)
        : device(gpu), format(pixel_format), width(w), height(h) {
        try {
            VkImageCreateInfo info{}; info.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
            info.imageType = VK_IMAGE_TYPE_2D; info.format = format; info.extent = {width, height, 1};
            info.mipLevels = 1; info.arrayLayers = 1; info.samples = VK_SAMPLE_COUNT_1_BIT;
            info.tiling = VK_IMAGE_TILING_OPTIMAL;
            info.usage = VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_STORAGE_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT;
            info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
            check(vkCreateImage(device, &info, nullptr, &handle), "Vulkan image creation failed");
            VkMemoryRequirements required{}; vkGetImageMemoryRequirements(device, handle, &required);
            VkMemoryDedicatedAllocateInfo dedicated{}; dedicated.sType = VK_STRUCTURE_TYPE_MEMORY_DEDICATED_ALLOCATE_INFO;
            dedicated.image = handle;
            VkMemoryAllocateInfo allocation{}; allocation.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
            allocation.pNext = &dedicated; allocation.allocationSize = required.size;
            allocation.memoryTypeIndex = memory_type(physical, required.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
            check(vkAllocateMemory(device, &allocation, nullptr, &memory), "Vulkan image allocation failed");
            check(vkBindImageMemory(device, handle, memory, 0), "Vulkan image binding failed");
            VkImageViewCreateInfo view_info{}; view_info.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
            view_info.image = handle; view_info.viewType = VK_IMAGE_VIEW_TYPE_2D; view_info.format = format;
            view_info.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
            check(vkCreateImageView(device, &view_info, nullptr, &view), "Vulkan image view creation failed");
        } catch (...) { close(); throw; }
    }
    Image(const Image&) = delete;
    Image& operator=(const Image&) = delete;
    void close() {
        if (view) vkDestroyImageView(device, view, nullptr);
        if (handle) vkDestroyImage(device, handle, nullptr);
        if (memory) vkFreeMemory(device, memory, nullptr);
        view = VK_NULL_HANDLE; handle = VK_NULL_HANDLE; memory = VK_NULL_HANDLE;
    }
    ~Image() { close(); }
};

// Declare this after resources it references, so its destructor waits before
// those resources are freed on any exception path.
struct Commands {
    VkDevice device;
    VkQueue queue = VK_NULL_HANDLE;
    VkCommandPool pool = VK_NULL_HANDLE;
    VkCommandBuffer handle = VK_NULL_HANDLE;
    VkFence fence = VK_NULL_HANDLE;
    Commands(VkDevice gpu, uint32_t family) : device(gpu) {
        try {
            vkGetDeviceQueue(device, family, 0, &queue);
            VkCommandPoolCreateInfo info{}; info.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
            info.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT; info.queueFamilyIndex = family;
            check(vkCreateCommandPool(device, &info, nullptr, &pool), "Vulkan command pool creation failed");
            VkCommandBufferAllocateInfo allocation{}; allocation.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
            allocation.commandPool = pool; allocation.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY; allocation.commandBufferCount = 1;
            check(vkAllocateCommandBuffers(device, &allocation, &handle), "Vulkan command buffer allocation failed");
            VkFenceCreateInfo fence_info{}; fence_info.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
            check(vkCreateFence(device, &fence_info, nullptr, &fence), "Vulkan fence creation failed");
        } catch (...) { close(); throw; }
    }
    Commands(const Commands&) = delete;
    Commands& operator=(const Commands&) = delete;
    void close() {
        if (queue) vkQueueWaitIdle(queue);
        if (fence) vkDestroyFence(device, fence, nullptr);
        if (pool) vkDestroyCommandPool(device, pool, nullptr);
        fence = VK_NULL_HANDLE; pool = VK_NULL_HANDLE;
    }
    ~Commands() { close(); }
    void begin() {
        check(vkResetCommandBuffer(handle, 0), "Vulkan command reset failed");
        VkCommandBufferBeginInfo info{}; info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
        info.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
        check(vkBeginCommandBuffer(handle, &info), "Vulkan command recording failed");
    }
    void finish() {
        check(vkEndCommandBuffer(handle), "Vulkan command close failed");
        check(vkResetFences(device, 1, &fence), "Vulkan fence reset failed");
        VkSubmitInfo info{}; info.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
        info.commandBufferCount = 1; info.pCommandBuffers = &handle;
        check(vkQueueSubmit(queue, 1, &info, fence), "Vulkan queue submission failed");
        check(vkWaitForFences(device, 1, &fence, VK_TRUE, 30000000000ull), "Vulkan GPU completion failed");
    }
    void image_barrier(Image& image, VkImageLayout layout, VkAccessFlags after) {
        VkImageMemoryBarrier barrier{}; barrier.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
        barrier.oldLayout = image.layout; barrier.newLayout = layout;
        barrier.srcAccessMask = image.layout == VK_IMAGE_LAYOUT_UNDEFINED ? 0 : VK_ACCESS_MEMORY_READ_BIT | VK_ACCESS_MEMORY_WRITE_BIT;
        barrier.dstAccessMask = after;
        barrier.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED; barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        barrier.image = image.handle; barrier.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
        vkCmdPipelineBarrier(handle, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, 0, 0, nullptr, 0, nullptr, 1, &barrier);
        image.layout = layout;
    }
    void buffer_barrier(Buffer& buffer, VkAccessFlags before, VkAccessFlags after) {
        VkBufferMemoryBarrier barrier{}; barrier.sType = VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER;
        barrier.srcAccessMask = before; barrier.dstAccessMask = after;
        barrier.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED; barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        barrier.buffer = buffer.handle; barrier.offset = 0; barrier.size = buffer.size;
        vkCmdPipelineBarrier(handle, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT | VK_PIPELINE_STAGE_HOST_BIT, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT | VK_PIPELINE_STAGE_HOST_BIT, 0, 0, nullptr, 1, &barrier, 0, nullptr);
    }
    void upload(Image& image, Buffer& buffer, VkDeviceSize offset = 0) {
        image_barrier(image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_ACCESS_TRANSFER_WRITE_BIT);
        VkBufferImageCopy copy{}; copy.bufferOffset = offset;
        copy.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1}; copy.imageExtent = {image.width, image.height, 1};
        vkCmdCopyBufferToImage(handle, buffer.handle, image.handle, image.layout, 1, &copy);
        image_barrier(image, VK_IMAGE_LAYOUT_GENERAL, VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT);
    }
    void download(Image& image, Buffer& buffer) {
        image_barrier(image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, VK_ACCESS_TRANSFER_READ_BIT);
        VkBufferImageCopy copy{}; copy.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
        copy.imageExtent = {image.width, image.height, 1};
        vkCmdCopyImageToBuffer(handle, image.handle, image.layout, buffer.handle, 1, &copy);
        buffer_barrier(buffer, VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_HOST_READ_BIT);
    }
};
}
