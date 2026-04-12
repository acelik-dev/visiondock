import { useStore } from "@/lib/store";
import { CheckCircle2, CircleDollarSign, ReceiptText, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function BillingView() {
  const { activePlan, setActivePlan, addEvent, notify } = useStore();

  const handlePlanChange = (plan: string) => {
    setActivePlan(plan);
    addEvent('Plan güncellendi', `${plan.toUpperCase()} planına geçiş yapıldı.`, 'blue');
    notify(`Plan ${plan} olarak güncellendi`);
  };

  const handleInvoice = () => {
    addEvent('Fatura oluşturuldu', 'Aylık kullanım faturası indirildi.', 'slate');
    notify("Fatura indiriliyor...");
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm relative overflow-hidden">
          {activePlan === 'starter' && <div className="absolute top-0 right-0 bg-blue-100 text-blue-700 text-[10px] font-bold px-3 py-1 uppercase tracking-wider rounded-bl-lg">Aktif</div>}
          <h3 className="text-lg font-bold text-slate-900 mb-1">Başlangıç</h3>
          <p className="text-sm text-slate-500 mb-4">Küçük ekipler ve test projeleri için.</p>
          <div className="text-3xl font-bold text-slate-900 mb-6">$49<span className="text-sm font-medium text-slate-500">/ay</span></div>
          
          <ul className="space-y-3 mb-6 text-sm text-slate-600">
            <li className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-emerald-500" /> 2 Aktif Proje</li>
            <li className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-emerald-500" /> Aylık 10 Saat GPU</li>
            <li className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-emerald-500" /> 10K API İsteği</li>
          </ul>
          
          <Button 
            variant={activePlan === 'starter' ? 'outline' : 'default'} 
            className="w-full"
            disabled={activePlan === 'starter'}
            onClick={() => handlePlanChange('starter')}
          >
            {activePlan === 'starter' ? 'Mevcut Plan' : 'Plana Geç'}
          </Button>
        </div>

        <div className="rounded-2xl border-2 border-blue-500 bg-white p-6 shadow-md relative overflow-hidden scale-105 z-10">
          {activePlan === 'pro' && <div className="absolute top-0 right-0 bg-blue-500 text-white text-[10px] font-bold px-3 py-1 uppercase tracking-wider rounded-bl-lg">Aktif</div>}
          <h3 className="text-lg font-bold text-slate-900 mb-1">Profesyonel</h3>
          <p className="text-sm text-slate-500 mb-4">Üretim ortamı ve yoğun kullanım için.</p>
          <div className="text-3xl font-bold text-slate-900 mb-6">$199<span className="text-sm font-medium text-slate-500">/ay</span></div>
          
          <ul className="space-y-3 mb-6 text-sm text-slate-600">
            <li className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-emerald-500" /> Sınırsız Proje</li>
            <li className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-emerald-500" /> Aylık 50 Saat GPU</li>
            <li className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-emerald-500" /> 100K API İsteği</li>
            <li className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-emerald-500" /> Edge Cihaz İndirme</li>
          </ul>
          
          <Button 
            className="w-full bg-blue-700 hover:bg-blue-800 text-white"
            disabled={activePlan === 'pro'}
            onClick={() => handlePlanChange('pro')}
          >
            {activePlan === 'pro' ? 'Mevcut Plan' : 'Plana Geç'}
          </Button>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm relative overflow-hidden">
          {activePlan === 'enterprise' && <div className="absolute top-0 right-0 bg-blue-100 text-blue-700 text-[10px] font-bold px-3 py-1 uppercase tracking-wider rounded-bl-lg">Aktif</div>}
          <h3 className="text-lg font-bold text-slate-900 mb-1">Kurumsal</h3>
          <p className="text-sm text-slate-500 mb-4">Özel gereksinimleri olan şirketler için.</p>
          <div className="text-3xl font-bold text-slate-900 mb-6">Özel</div>
          
          <ul className="space-y-3 mb-6 text-sm text-slate-600">
            <li className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-emerald-500" /> Dedicated A100 GPU</li>
            <li className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-emerald-500" /> SLA & 7/24 Destek</li>
            <li className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-emerald-500" /> Özel On-Prem Dağıtım</li>
          </ul>
          
          <Button 
            variant="outline"
            className="w-full"
            onClick={() => {
              addEvent('Kurumsal satış talebi', 'Satış ekibiyle iletişime geçildi.', 'slate');
              notify("Satış ekibi yönlendiriliyor");
            }}
          >
            İletişime Geç
          </Button>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-lg font-bold text-slate-900 mb-4">Ödeme Yöntemi ve Geçmişi</h3>
        
        <div className="flex items-center justify-between p-4 rounded-xl border border-slate-200 bg-slate-50 mb-6">
          <div className="flex items-center gap-4">
            <div className="h-10 w-14 bg-white border border-slate-200 rounded shadow-sm flex items-center justify-center font-bold text-slate-800 italic">
              VISA
            </div>
            <div>
              <div className="font-bold text-slate-900">•••• •••• •••• 4242</div>
              <div className="text-xs text-slate-500">Son Kullanma: 12/25</div>
            </div>
          </div>
          <Button variant="ghost" onClick={() => notify("Kart güncelleme açıldı")}>Güncelle</Button>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between p-3 border-b border-slate-100 last:border-0">
            <div className="flex items-center gap-3">
              <ReceiptText className="h-5 w-5 text-slate-400" />
              <div>
                <div className="font-semibold text-slate-900 text-sm">Ekim 2023 - Profesyonel Plan</div>
                <div className="text-xs text-slate-500">12 Eki 2023 • Başarılı</div>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="font-bold text-slate-900">$199.00</div>
              <Button variant="ghost" size="sm" onClick={handleInvoice}>İndir</Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
