import { useStore } from "@/lib/store";
import { AlertCircle, BoxSelect, CheckCircle2, ChevronRight, CircleDollarSign, Clock, Database, FileImage, FileJson, Folder, Layers, Server, Sparkles, UploadCloud } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusPill } from "@/components/layout";

export default function ProjectsView() {
  const { 
    workflowStep, 
    setWorkflowStep, 
    taskText, 
    setTaskText,
    datasetUploaded,
    setDatasetUploaded,
    syntheticGenerated,
    setSyntheticGenerated,
    trainingStarted,
    setTrainingStarted,
    addEvent
  } = useStore();

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-4 gap-5">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Durum</div>
          <div className="mt-3 flex items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-full ${trainingStarted ? 'bg-emerald-600' : datasetUploaded ? 'bg-blue-600' : 'bg-amber-500'}`} />
            <span className="text-lg font-bold text-slate-950">{trainingStarted ? 'Eğitimde' : datasetUploaded ? 'Veri Hazır' : 'Yapılandırılıyor'}</span>
          </div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Proje ID</div>
          <div className="mt-3 font-mono text-lg font-bold text-blue-700">PRJ-8821</div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Oluşturulan Model</div>
          <div className="mt-3 text-lg font-bold text-slate-950">{trainingStarted ? 1 : 0}</div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Veri Seti Boyutu</div>
          <div className={`mt-3 text-lg font-bold ${datasetUploaded ? 'text-slate-950' : 'text-slate-400'}`}>{datasetUploaded ? '18.4 GB' : 'Yüklenmedi'}</div>
        </div>
      </div>

      {workflowStep === 1 && (
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="border-b border-slate-200 bg-slate-50 px-8 py-5">
            <h3 className="flex items-center gap-3 text-xl font-bold text-slate-950">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-700 text-sm font-bold text-white">1</span>
              Görev Tanımı
            </h3>
            <p className="mt-2 max-w-2xl text-sm text-slate-600">Problemi doğal dille tarif edin. VisionDock, görev tipini ve uygun model ailesini buna göre önerir.</p>
          </div>
          <div className="p-8">
            <textarea
              value={taskText}
              onChange={(e) => setTaskText(e.target.value)}
              placeholder="Örn. Montaj hattındaki metal parçalarda çizik, göçük ve eksik vida durumlarını tespit et..."
              className="h-36 w-full resize-none rounded-xl border border-slate-300 bg-white p-5 text-base text-slate-900 shadow-sm outline-none transition-all placeholder:text-slate-400 focus:border-blue-600 focus:ring-4 focus:ring-blue-100"
            />

            <div className="mt-8">
              <h4 className="mb-4 text-xs font-bold uppercase tracking-widest text-slate-500">Örnekler</h4>
              <div className="grid grid-cols-3 gap-5">
                <button onClick={() => { setTaskText('Ürünleri görsel kalite kriterlerine göre Geçti veya Kaldı olarak sınıflandır.'); addEvent('Sınıflandırma örneği seçildi', 'Görev açıklaması otomatik dolduruldu.', 'blue'); }} className="rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md cursor-pointer">
                  <Layers className="mb-3 h-6 w-6 text-blue-700" />
                  <div className="mb-1 text-sm font-bold text-slate-950">Sınıflandırma</div>
                  <div className="text-xs text-slate-500">Tüm görüntüyü kategoriye ayırır</div>
                </button>
                <button onClick={() => { setTaskText('Forklift, operatör ve güvenlik konilerinin etrafına sınırlayıcı kutular çizerek tespit et.'); addEvent('Nesne tespiti örneği seçildi', 'Görev açıklaması otomatik dolduruldu.', 'blue'); }} className="rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md cursor-pointer">
                  <BoxSelect className="mb-3 h-6 w-6 text-cyan-700" />
                  <div className="mb-1 text-sm font-bold text-slate-950">Nesne Tespiti</div>
                  <div className="text-xs text-slate-500">Belirli nesneleri konumlandırır</div>
                </button>
                <button onClick={() => { setTaskText('Normal üretim referansından sapan görsel anomalileri belirle.'); addEvent('Anomali tespiti örneği seçildi', 'Görev açıklaması otomatik dolduruldu.', 'blue'); }} className="rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md cursor-pointer">
                  <AlertCircle className="mb-3 h-6 w-6 text-red-600" />
                  <div className="mb-1 text-sm font-bold text-slate-950">Anomali Tespiti</div>
                  <div className="text-xs text-slate-500">Beklenmeyen kusurları bulur</div>
                </button>
              </div>
            </div>

            <div className="mt-10 flex justify-end border-t border-slate-200 pt-6">
              <Button onClick={() => { setWorkflowStep(2); addEvent('Görev tanımı kaydedildi', 'Kullanıcı veri seti yükleme adımına geçti.', 'green'); }} className="w-40 group bg-blue-700 text-white hover:bg-blue-800">
                Sonraki Adım <ChevronRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
              </Button>
            </div>
          </div>
        </div>
      )}

      {workflowStep === 2 && (
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="border-b border-slate-200 bg-slate-50 px-8 py-5">
            <h3 className="flex items-center gap-3 text-xl font-bold text-slate-950">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-700 text-sm font-bold text-white">2</span>
              Veri Seti Yükleme
            </h3>
            <p className="mt-2 text-sm text-slate-600">Görüntü ve etiket dosyalarını yükleyin. <span className="font-bold text-amber-700">Her .zip için 32GB limit</span></p>
          </div>
          <div className="p-8">
            <button onClick={() => { setDatasetUploaded(true); addEvent('Veri seti yüklendi', '18.4 GB büyüklüğünde dataset.zip algılandı ve klasör yapısı doğrulandı.', 'green'); }} className={`flex w-full cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-12 text-center transition-all ${datasetUploaded ? 'border-emerald-300 bg-emerald-50' : 'border-slate-300 bg-slate-50 hover:border-blue-400 hover:bg-blue-50/40'}`}>
              <div className="mb-5 flex h-20 w-20 items-center justify-center rounded-full border border-slate-200 bg-white shadow-sm">
                {datasetUploaded ? <CheckCircle2 className="h-10 w-10 text-emerald-700" /> : <UploadCloud className="h-10 w-10 text-blue-700" />}
              </div>
              <h4 className="mb-2 text-lg font-bold text-slate-950">{datasetUploaded ? 'dataset.zip yüklendi' : 'Veri setinizi buraya sürükleyip bırakın'}</h4>
              <p className="mb-6 text-sm text-slate-500">{datasetUploaded ? '18.4 GB, 12.840 görüntü, 12.840 etiket dosyası doğrulandı.' : 'YOLO formatı, COCO JSON veya klasör yapılı görüntü setleri desteklenir.'}</p>
              <Button variant={datasetUploaded ? 'default' : 'outline'} className={datasetUploaded ? "bg-emerald-700 hover:bg-emerald-800 text-white" : ""}>{datasetUploaded ? 'Yükleme Tamamlandı' : 'Dosya Seç'}</Button>
            </button>

            <div className="mt-8 grid grid-cols-5 gap-6">
              <div className="col-span-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <h5 className="mb-4 flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-slate-500"><Database className="h-4 w-4 text-blue-700" /> Klasör Algılama</h5>
                <div className="space-y-1.5 rounded-xl border border-slate-200 bg-slate-50 p-4 font-mono text-sm text-slate-600">
                  <div className="flex items-center gap-2"><Folder className="h-4 w-4 text-slate-500" /> dataset/ <StatusPill tone={datasetUploaded ? 'green' : 'slate'}>{datasetUploaded ? 'algılandı' : 'bekleniyor'}</StatusPill></div>
                  <div className="flex items-center gap-2 pl-6"><Folder className="h-4 w-4 text-blue-700" /> images/</div>
                  <div className="flex items-center gap-2 pl-12"><FileImage className="h-4 w-4 text-slate-400" /> img_001.jpg</div>
                  <div className="flex items-center gap-2 pl-12"><FileImage className="h-4 w-4 text-slate-400" /> img_002.jpg</div>
                  <div className="flex items-center gap-2 pl-6"><Folder className="h-4 w-4 text-emerald-700" /> labels/</div>
                  <div className="flex items-center gap-2 pl-12"><FileJson className="h-4 w-4 text-slate-400" /> img_001.txt</div>
                  <div className="flex items-center gap-2 pl-12"><FileJson className="h-4 w-4 text-slate-400" /> img_002.txt</div>
                </div>
              </div>

              <div className={`col-span-2 flex flex-col justify-center rounded-2xl border p-6 text-center shadow-sm ${syntheticGenerated ? 'border-emerald-200 bg-emerald-50' : 'border-blue-200 bg-blue-50'}`}>
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-xl border border-blue-200 bg-white shadow-sm">
                  {syntheticGenerated ? <CheckCircle2 className="h-7 w-7 text-emerald-700" /> : <Sparkles className="h-7 w-7 text-blue-700" />}
                </div>
                <h5 className="mb-2 text-base font-bold text-slate-950">Verin yetersiz mi?</h5>
                <p className="mb-6 text-sm leading-relaxed text-slate-600">{syntheticGenerated ? 'Sentetik 2.400 ek görüntü üretim kuyruğuna alındı.' : 'Üretken yapay zeka ile sentetik veri üret.'}</p>
                <Button variant={syntheticGenerated ? 'default' : 'secondary'} className={`w-full ${syntheticGenerated ? 'bg-emerald-700 hover:bg-emerald-800 text-white' : 'bg-slate-900 text-white hover:bg-slate-800'}`} onClick={() => { setSyntheticGenerated(true); addEvent('Sentetik veri üretimi başlatıldı', '2.400 ek üretim görüntüsü oluşturma kuyruğuna alındı.', 'green'); }}>{syntheticGenerated ? 'Sentetik Veri Hazırlandı' : 'Sentetik Veri Üret'}</Button>
              </div>
            </div>

            <div className="mt-10 flex items-center justify-between border-t border-slate-200 pt-6">
              <Button variant="ghost" onClick={() => setWorkflowStep(1)}>Geri</Button>
              <Button onClick={() => { setWorkflowStep(3); addEvent('Veri seti onaylandı', 'Model öneri ve eğitim onayı adımına geçildi.', 'green'); }} className="w-40 group bg-blue-700 text-white hover:bg-blue-800">Sonraki Adım <ChevronRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" /></Button>
            </div>
          </div>
        </div>
      )}

      {workflowStep === 3 && (
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="border-b border-slate-200 bg-slate-50 px-8 py-5">
            <h3 className="flex items-center gap-3 text-xl font-bold text-slate-950">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-700 text-sm font-bold text-white">3</span>
              Model Önerisi ve Eğitim
            </h3>
            <p className="mt-2 text-sm text-slate-600">Eğitimi başlatmadan önce model önerisini, GPU tahsisini ve tahmini maliyeti onaylayın.</p>
          </div>
          <div className="p-8">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-6">
              <div className="mb-6 flex items-center justify-between border-b border-slate-200 pb-6">
                <div>
                  <div className="text-xs font-bold uppercase tracking-widest text-slate-500">Önerilen Model Mimarisi</div>
                  <div className="mt-2 text-2xl font-bold text-slate-950">YOLOv8 Medium</div>
                </div>
                <div className="text-right">
                  <div className="text-xs font-bold uppercase tracking-widest text-slate-500">Görev Tipi</div>
                  <div className="mt-2 text-lg font-bold text-slate-950">Nesne Tespiti</div>
                </div>
              </div>

              <h4 className="mb-4 text-xs font-bold uppercase tracking-widest text-slate-500">Kaynak Tahsisi</h4>
              <div className="grid grid-cols-3 gap-5">
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-500"><Server className="h-4 w-4" /> Hesaplama Birimi</div>
                  <div className="font-bold text-slate-950">1x NVIDIA A100</div>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-500"><Clock className="h-4 w-4" /> Tahmini Süre</div>
                  <div className="font-bold text-slate-950">~4.5 Saat</div>
                </div>
                <div className="rounded-xl border border-emerald-200 bg-white p-4 shadow-sm">
                  <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-500"><CircleDollarSign className="h-4 w-4 text-emerald-700" /> Maliyet Tahmini</div>
                  <div className="font-bold text-emerald-700">$12.40</div>
                </div>
              </div>
              {trainingStarted && (
                <div className="mt-6 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                  <div className="mb-2 flex items-center justify-between text-sm font-bold text-emerald-800">
                    <span>Eğitim çalışması başlatıldı</span>
                    <span>%18</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-emerald-100">
                    <div className="h-full w-[18%] rounded-full bg-emerald-700" />
                  </div>
                </div>
              )}
            </div>

            <div className="mt-10 flex items-center justify-between border-t border-slate-200 pt-6">
              <Button variant="ghost" onClick={() => setWorkflowStep(2)}>Geri</Button>
              <Button 
                onClick={() => { 
                  setTrainingStarted(true); 
                  addEvent('Eğitim başlatıldı', 'YOLOv8 Medium modeli A100 düğümünde eğitime alındı.', 'blue'); 
                }} 
                className="w-40 bg-blue-700 text-white hover:bg-blue-800"
                disabled={trainingStarted}
              >
                {trainingStarted ? 'Eğitim Başladı' : 'Eğitimi Başlat'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
