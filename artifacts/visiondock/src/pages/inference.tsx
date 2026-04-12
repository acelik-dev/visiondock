import { useStore } from "@/lib/store";
import { Cloud, Copy, Cpu, Download } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function InferenceView() {
  const { addEvent, notify } = useStore();

  const handleCopyEndpoint = () => {
    addEvent('API Uç noktası kopyalandı', 'Canlı çıkarım uç noktası panoya kopyalandı.', 'slate');
    notify("API adresi panoya kopyalandı");
  };

  const handleDownloadDocker = () => {
    addEvent('Docker imajı oluşturuldu', 'Edge cihazlar için optimize edilmiş konteyner dışa aktarıldı.', 'green');
    notify("Docker imajı indirme başlatıldı");
  };

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-bold text-slate-900 mb-2">Modeli Dağıt</h2>
        <p className="text-slate-600 mb-8">Eğittiğiniz modeli bulut tabanlı API olarak veya edge cihazlarınızda yerel olarak çalıştırın.</p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-6 relative overflow-hidden">
            <div className="absolute top-0 right-0 p-6 opacity-10">
              <Cloud className="w-32 h-32 text-blue-700" />
            </div>
            <div className="relative z-10">
              <div className="h-12 w-12 bg-white rounded-lg border border-blue-200 flex items-center justify-center mb-4 shadow-sm">
                <Cloud className="h-6 w-6 text-blue-700" />
              </div>
              <h3 className="text-lg font-bold text-slate-900 mb-2">Bulut API (REST)</h3>
              <p className="text-sm text-slate-600 mb-6">Yüksek erişilebilirlik ve otomatik ölçeklenen çıkarım uç noktası. İnternete bağlı herhangi bir cihazdan istek atın.</p>
              
              <div className="bg-slate-900 rounded-lg p-4 font-mono text-xs text-slate-300 mb-4 flex items-center justify-between">
                <span className="truncate mr-4">https://api.visiondock.ai/v1/infer/prj-8821</span>
                <button onClick={handleCopyEndpoint} className="text-slate-400 hover:text-white transition-colors shrink-0">
                  <Copy className="h-4 w-4" />
                </button>
              </div>
              
              <Button onClick={handleCopyEndpoint} className="w-full bg-blue-700 text-white hover:bg-blue-800">API Anahtarı Oluştur</Button>
            </div>
          </div>

          <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-6 relative overflow-hidden">
            <div className="absolute top-0 right-0 p-6 opacity-10">
              <Cpu className="w-32 h-32 text-emerald-700" />
            </div>
            <div className="relative z-10">
              <div className="h-12 w-12 bg-white rounded-lg border border-emerald-200 flex items-center justify-center mb-4 shadow-sm">
                <Cpu className="h-6 w-6 text-emerald-700" />
              </div>
              <h3 className="text-lg font-bold text-slate-900 mb-2">Edge (Yerel) Dağıtım</h3>
              <p className="text-sm text-slate-600 mb-6">Fabrika zemininde, internet olmadan sıfır gecikme ile çalışmak için Docker konteyneri olarak indirin (NVIDIA Jetson, x86 IPC).</p>
              
              <div className="grid grid-cols-2 gap-3 mb-4">
                <div className="bg-white border border-slate-200 rounded-lg p-3 flex flex-col items-center justify-center text-center shadow-sm">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">Format</span>
                  <span className="font-mono text-sm font-bold text-slate-900">TensorRT</span>
                </div>
                <div className="bg-white border border-slate-200 rounded-lg p-3 flex flex-col items-center justify-center text-center shadow-sm">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">Boyut</span>
                  <span className="font-mono text-sm font-bold text-slate-900">1.2 GB</span>
                </div>
              </div>
              
              <Button onClick={handleDownloadDocker} className="w-full bg-emerald-700 text-white hover:bg-emerald-800">
                <Download className="mr-2 h-4 w-4" />
                Docker İmajını İndir
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
