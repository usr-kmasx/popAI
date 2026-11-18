// Linux Vulkan discovery. NCNN enumerates these physical devices in this order.
#include <vulkan/vulkan.h>
#include <cstdio>
#include <cstring>
#include <vector>
static void quoted(const char* s) {
    putchar('"'); for (; *s; ++s) { if (*s == '"' || *s == '\\') putchar('\\'); if ((unsigned char)*s >= 32) putchar(*s); } putchar('"');
}
int main() {
    VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO}; app.apiVersion=VK_API_VERSION_1_1;
    VkInstanceCreateInfo ci{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO}; ci.pApplicationInfo=&app;
    VkInstance instance; if (vkCreateInstance(&ci,nullptr,&instance)!=VK_SUCCESS) return 1;
    uint32_t count=0; if(vkEnumeratePhysicalDevices(instance,&count,nullptr)!=VK_SUCCESS) return 2;
    std::vector<VkPhysicalDevice> devices(count); vkEnumeratePhysicalDevices(instance,&count,devices.data());
    puts("[");
    for(uint32_t i=0;i<count;i++) {
        VkPhysicalDeviceIDProperties id{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_ID_PROPERTIES};
        VkPhysicalDeviceProperties2 p{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2}; p.pNext=&id;
        vkGetPhysicalDeviceProperties2(devices[i],&p);
        uint32_t n=0; vkEnumerateDeviceExtensionProperties(devices[i],nullptr,&n,nullptr);
        std::vector<VkExtensionProperties> exts(n); vkEnumerateDeviceExtensionProperties(devices[i],nullptr,&n,exts.data());
        bool budget=false; for(auto &e:exts) if(!strcmp(e.extensionName,VK_EXT_MEMORY_BUDGET_EXTENSION_NAME)) budget=true;
        VkPhysicalDeviceMemoryBudgetPropertiesEXT b{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_MEMORY_BUDGET_PROPERTIES_EXT};
        VkPhysicalDeviceMemoryProperties2 m{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_MEMORY_PROPERTIES_2}; if(budget) m.pNext=&b;
        vkGetPhysicalDeviceMemoryProperties2(devices[i],&m);
        unsigned long long total=0,free=0;
        for(uint32_t h=0;h<m.memoryProperties.memoryHeapCount;h++) if(m.memoryProperties.memoryHeaps[h].flags&VK_MEMORY_HEAP_DEVICE_LOCAL_BIT) {
            total+=m.memoryProperties.memoryHeaps[h].size;
            if(budget) free+=b.heapBudget[h]>b.heapUsage[h]?b.heapBudget[h]-b.heapUsage[h]:0;
        }
        printf("{\"index\":%u,\"name\":",i); quoted(p.properties.deviceName);
        printf(",\"uuid\":\""); for(auto c:id.deviceUUID) printf("%02x",c);
        printf("\",\"type\":%u,\"total\":%llu,\"free\":",p.properties.deviceType,total);
        if(budget) printf("%llu",free); else printf("null");
        printf("}%s\n",i+1<count?",":"");
    }
    puts("]"); vkDestroyInstance(instance,nullptr); return 0;
}
