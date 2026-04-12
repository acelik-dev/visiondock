import { useStore } from "@/lib/store";
import { Download, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function ModelsView() {
  const { models, deleteModel, addEvent, notify } = useStore();

  const handleImport = () => {
    addEvent('Model içe aktarıldı', 'Yeni bir dış model kütüphaneye eklendi.', 'blue');
    notify("Model içe aktarma diyaloğu açıldı");
  };

  const handleDelete = (id: number, name: string) => {
    deleteModel(id);
    addEvent('Model silindi', `${name} kütüphaneden kaldırıldı.`, 'red');
    notify(`${name} silindi`);
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      <div className="flex items-center justify-between border-b border-slate-200 px-6 py-5">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Eğitilmiş ve Hazır Modeller</h2>
          <p className="text-sm text-slate-500">Projelerinizden elde edilen ve önceden eğitilmiş modeller.</p>
        </div>
        <Button onClick={handleImport} className="bg-slate-900 text-white hover:bg-slate-800">
          <Plus className="mr-2 h-4 w-4" /> Dışarıdan Model Ekle
        </Button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-6 py-4 font-bold tracking-wider">Model Adı</th>
              <th className="px-6 py-4 font-bold tracking-wider">Görev Tipi</th>
              <th className="px-6 py-4 font-bold tracking-wider">Parametreler</th>
              <th className="px-6 py-4 font-bold tracking-wider">Doğruluk</th>
              <th className="px-6 py-4 font-bold tracking-wider">Çözünürlük</th>
              <th className="px-6 py-4 font-bold tracking-wider text-right">İşlemler</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {models.map((model) => (
              <tr key={model.id} className="hover:bg-slate-50/50 transition-colors">
                <td className="px-6 py-4 font-mono font-bold text-slate-900">{model.name}</td>
                <td className="px-6 py-4"><span className="inline-flex rounded-md bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">{model.type}</span></td>
                <td className="px-6 py-4 font-medium text-slate-600">{model.params}</td>
                <td className="px-6 py-4 font-medium text-emerald-700">{model.accuracy}</td>
                <td className="px-6 py-4 font-medium text-slate-600">{model.res}</td>
                <td className="px-6 py-4 text-right">
                  <div className="flex justify-end gap-2">
                    <Button variant="ghost" size="icon" onClick={() => notify(`${model.name} ağırlıkları indiriliyor`)}>
                      <Download className="h-4 w-4 text-slate-500" />
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => handleDelete(model.id, model.name)}>
                      <Trash2 className="h-4 w-4 text-red-500" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
            {models.length === 0 && (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-slate-500">Kütüphanede model bulunmuyor.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
